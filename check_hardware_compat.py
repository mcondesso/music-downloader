"""
Script to check audio files for compatibility with hardware DJ players
(Pioneer/AlphaTheta CDJ/XDJ and similar embedded decoders).

Desktop software uses lenient decoders and will happily play files that
hardware players reject with "unsupported file format" errors (E-8305 family).
This script detects the known file-level causes before the files reach a
player:

  * fragmented DASH MP4 containers (YouTube downloads)      -> remux
  * wrong codec inside the container (HE-AAC, Opus, ALAC)   -> re-encode
  * WAV traps: 32-bit/float samples, WAVE_FORMAT_EXTENSIBLE -> convert
  * out-of-range sample rates (22.05 kHz, > 48 kHz)         -> resample
  * formats with no hardware support at all (.ogg/.opus)    -> re-encode
  * mislabeled files (extension does not match the content)

Usage:
    poetry run python check_hardware_compat.py <file_or_directory> [--all]

Exit code is 0 when every scanned file passes, 1 when any file FAILs.
Requires ffprobe (installed together with ffmpeg).
"""

import argparse
import json
import os
import shutil
import struct
import subprocess
import sys

AUDIO_EXTENSIONS = {
    ".mp3",
    ".mp4",
    ".m4a",
    ".m4p",
    ".aac",
    ".wav",
    ".aif",
    ".aiff",
    ".aifc",
    ".flac",
    ".ogg",
    ".opus",
    ".webm",
}

# Sample rates in the guaranteed envelope of every Pioneer/AlphaTheta player
SAFE_SAMPLE_RATES = {44100, 48000}
# Accepted for lossless formats by newer players only (CDJ-3000, NXS2, XDJ-AZ)
HIRES_SAMPLE_RATES = {88200, 96000}

FAIL = "FAIL"
WARN = "WARN"


def _ffprobe(filepath: str) -> dict | None:
    """Run ffprobe and return the parsed JSON, or None if the file cannot be parsed."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            filepath,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)


def _scan_mp4_boxes(filepath: str) -> list[str]:
    """Return the top-level MP4 box names, e.g. ['ftyp', 'moov', 'mdat']."""
    boxes = []
    size = os.path.getsize(filepath)
    pos = 0
    with open(filepath, "rb") as file:
        while pos < size - 8:
            file.seek(pos)
            header = file.read(8)
            if len(header) < 8:
                break
            (box_size,) = struct.unpack(">I", header[:4])
            name = header[4:8].decode("latin1")
            if box_size == 1:  # 64-bit box size
                (box_size,) = struct.unpack(">Q", file.read(8))
            if box_size < 8:
                break
            boxes.append(name)
            pos += box_size
    return boxes


def _check_mp4(filepath: str, probe: dict) -> list[tuple[str, str]]:
    """Check .mp4/.m4a files: container structure and codec."""
    findings = []

    boxes = _scan_mp4_boxes(filepath)
    if "moof" in boxes or "sidx" in boxes or "styp" in boxes:
        findings.append(
            (
                FAIL,
                "fragmented DASH MP4 container - hardware players cannot parse it. "
                'Fix (lossless): ffmpeg -i in -c copy -movflags +faststart out.m4a',
            )
        )
    if boxes.count("moov") > 1:
        findings.append((FAIL, "multiple moov atoms - remux the file"))
    if boxes and boxes[0] != "ftyp":
        findings.append((WARN, "container does not start with an ftyp box"))

    audio_streams = [s for s in probe["streams"] if s["codec_type"] == "audio"]
    video_streams = [
        s
        for s in probe["streams"]
        if s["codec_type"] == "video"
        and not s.get("disposition", {}).get("attached_pic")
    ]
    if video_streams:
        findings.append(
            (
                WARN,
                f"contains a video track ({video_streams[0].get('codec_name')}) - "
                "strip it: ffmpeg -i in -map 0:a:0 -c copy out.m4a",
            )
        )
    if len(audio_streams) > 1:
        findings.append((WARN, f"{len(audio_streams)} audio tracks - keep only the first"))
    if not audio_streams:
        findings.append((FAIL, "no audio track found"))
        return findings

    audio = audio_streams[0]
    codec = audio.get("codec_name")
    profile = audio.get("profile") or ""
    if codec == "aac":
        if "HE" in profile or "SBR" in profile:
            findings.append(
                (FAIL, f"AAC profile is {profile} - players decode AAC-LC only. Re-encode.")
            )
    elif codec == "alac":
        findings.append(
            (
                WARN,
                "ALAC - plays on 2016+ players (XDJ-1000MK2, NXS2, CDJ-3000, XDJ-AZ) "
                "but fails on older gear (CDJ-850/900/2000, XDJ-1000 mk1)",
            )
        )
    elif codec in ("opus", "vorbis"):
        findings.append((FAIL, f"{codec} audio in MP4 - no hardware player supports it. Re-encode to AAC-LC."))
    else:
        findings.append((FAIL, f"unexpected codec '{codec}' in MP4 container"))

    findings.extend(_check_rate_and_channels(audio, lossless=False))
    return findings


def _check_wav(filepath: str) -> list[tuple[str, str]]:
    """Check WAV files by parsing the RIFF fmt chunk directly.

    ffprobe's codec label hides the difference between plain PCM and
    WAVE_FORMAT_EXTENSIBLE headers, and hardware players reject the latter,
    so the header bytes are the only reliable source of truth here.
    """
    findings = []
    with open(filepath, "rb") as file:
        header = file.read(12)
        if header[:4] != b"RIFF" or header[8:12] != b"WAVE":
            return [(FAIL, "not a RIFF/WAVE file despite the .wav extension")]
        # Walk chunks to find fmt
        while True:
            chunk_header = file.read(8)
            if len(chunk_header) < 8:
                return [(FAIL, "no fmt chunk found - corrupt WAV header")]
            chunk_id = chunk_header[:4]
            (chunk_size,) = struct.unpack("<I", chunk_header[4:])
            if chunk_id == b"fmt ":
                fmt = file.read(min(chunk_size, 40))
                break
            file.seek(chunk_size + (chunk_size & 1), os.SEEK_CUR)

    format_tag, channels, sample_rate, _, _, bits = struct.unpack("<HHIIHH", fmt[:16])

    if format_tag == 0xFFFE:  # WAVE_FORMAT_EXTENSIBLE
        sub_format = fmt[24:26] if len(fmt) >= 26 else b""
        if sub_format == b"\x01\x00":  # PCM sub-format GUID starts 01 00
            findings.append(
                (
                    FAIL,
                    "WAVE_FORMAT_EXTENSIBLE header (0xFFFE) - the audio is plain PCM "
                    "but players reject the header (common with Bandcamp/DAW exports). "
                    "Fix: rewrite header bytes 20-21 to 01 00, or re-export the file.",
                )
            )
        elif sub_format == b"\x03\x00":
            findings.append(
                (FAIL, "32-bit float WAV (EXTENSIBLE) - no player supports it. Convert to 16/24-bit PCM.")
            )
        else:
            findings.append((FAIL, "WAVE_FORMAT_EXTENSIBLE with a non-PCM sub-format"))
    elif format_tag == 0x0003:
        findings.append((FAIL, "32-bit float WAV - no player supports it. Convert to 16/24-bit PCM."))
    elif format_tag != 0x0001:
        findings.append((FAIL, f"non-PCM WAV format tag 0x{format_tag:04X}"))

    if bits not in (16, 24):
        findings.append(
            (FAIL, f"{bits}-bit samples - players support 16/24-bit WAV only. Convert.")
        )
    if channels > 2:
        findings.append((FAIL, f"{channels} channels - downmix to stereo"))
    if sample_rate not in SAFE_SAMPLE_RATES:
        if sample_rate in HIRES_SAMPLE_RATES:
            findings.append(
                (WARN, f"{sample_rate} Hz - only 2016+ players accept it; older gear caps at 48 kHz")
            )
        else:
            findings.append((FAIL, f"{sample_rate} Hz sample rate is outside every player's range"))

    if os.path.getsize(filepath) > 4 * 1024**3:
        findings.append((FAIL, "file exceeds the FAT32 4 GB limit"))
    return findings


def _check_mp3(filepath: str, probe: dict) -> list[tuple[str, str]]:
    findings = []
    audio = next((s for s in probe["streams"] if s["codec_type"] == "audio"), None)
    if audio is None:
        return [(FAIL, "no audio stream found")]
    if audio.get("codec_name") != "mp3":
        findings.append(
            (
                FAIL,
                f"content is {audio.get('codec_name')}, not MP3 - mislabeled file "
                "(common with converter websites). Re-encode or fix the extension.",
            )
        )
        return findings
    findings.extend(_check_rate_and_channels(audio, lossless=False))
    # Oversized ID3v2 tags have been linked to load failures on CDJs
    with open(filepath, "rb") as file:
        head = file.read(10)
    if head[:3] == b"ID3":
        tag_size = (head[6] << 21) | (head[7] << 14) | (head[8] << 7) | head[9]
        if tag_size > 2 * 1024**2:
            findings.append(
                (WARN, f"very large ID3v2 tag ({tag_size // 1024} KiB) - strip oversized artwork/tags")
            )
    return findings


def _check_flac(filepath: str, probe: dict) -> list[tuple[str, str]]:
    findings = []
    with open(filepath, "rb") as file:
        magic = file.read(4)
    if magic[:3] == b"ID3":
        findings.append(
            (FAIL, "ID3 tag prepended to FLAC - strict parsers reject it. Rewrite: ffmpeg -i in -c copy out.flac")
        )
    elif magic != b"fLaC":
        findings.append((FAIL, "not a native FLAC file despite the extension"))
    audio = next((s for s in probe["streams"] if s["codec_type"] == "audio"), None)
    if audio:
        findings.extend(_check_rate_and_channels(audio, lossless=True))
        bits = int(audio.get("bits_per_raw_sample") or audio.get("bits_per_sample") or 16)
        if bits > 24:
            findings.append((FAIL, f"{bits}-bit FLAC - players support up to 24-bit"))
    findings.append(
        (WARN, "FLAC only plays on 2016+ players (XDJ-1000MK2, NXS2, CDJ-3000, XDJ-AZ)")
    )
    return findings


def _check_aiff(filepath: str, probe: dict) -> list[tuple[str, str]]:
    findings = []
    audio = next((s for s in probe["streams"] if s["codec_type"] == "audio"), None)
    if audio is None:
        return [(FAIL, "no audio stream found")]
    if audio.get("codec_name") not in ("pcm_s16be", "pcm_s24be"):
        findings.append(
            (FAIL, f"AIFF codec {audio.get('codec_name')} - only uncompressed 16/24-bit PCM plays")
        )
    if filepath.lower().endswith(".aifc"):
        findings.append(
            (WARN, "'.aifc' extension is rejected even when uncompressed - rename to .aiff")
        )
    findings.extend(_check_rate_and_channels(audio, lossless=True))
    return findings


def _check_rate_and_channels(audio: dict, lossless: bool) -> list[tuple[str, str]]:
    findings = []
    sample_rate = int(audio.get("sample_rate") or 0)
    if sample_rate not in SAFE_SAMPLE_RATES:
        if lossless and sample_rate in HIRES_SAMPLE_RATES:
            findings.append(
                (WARN, f"{sample_rate} Hz - only 2016+ players accept it; older gear caps at 48 kHz")
            )
        else:
            findings.append(
                (FAIL, f"{sample_rate} Hz sample rate - players require 44.1/48 kHz. Resample.")
            )
    if int(audio.get("channels") or 0) > 2:
        findings.append((FAIL, f"{audio.get('channels')} channels - downmix to stereo"))
    return findings


def check_file(filepath: str) -> list[tuple[str, str]]:
    """Run the appropriate checks for one file and return (level, message) findings."""
    ext = os.path.splitext(filepath)[1].lower()

    if ext in (".ogg", ".opus", ".webm"):
        return [(FAIL, f"'{ext}' has no hardware player support at all - re-encode to AAC-LC or MP3")]
    if ext == ".m4p":
        return [(FAIL, "DRM-protected iTunes file - cannot be fixed, re-source the track")]

    if ext == ".wav":
        return _check_wav(filepath)

    probe = _ffprobe(filepath)
    if probe is None:
        return [(FAIL, "ffprobe cannot parse this file - it is corrupt or not audio")]

    if ext in (".mp4", ".m4a"):
        return _check_mp4(filepath, probe)
    if ext == ".aac":
        return _check_adts(filepath, probe)
    if ext == ".mp3":
        return _check_mp3(filepath, probe)
    if ext == ".flac":
        return _check_flac(filepath, probe)
    if ext in (".aif", ".aiff", ".aifc"):
        return _check_aiff(filepath, probe)
    return []


def _check_adts(filepath: str, probe: dict) -> list[tuple[str, str]]:
    """Check raw .aac (ADTS) files."""
    findings = []
    audio = next((s for s in probe["streams"] if s["codec_type"] == "audio"), None)
    if audio is None:
        return [(FAIL, "no audio stream found")]
    profile = audio.get("profile") or ""
    if "HE" in profile or "SBR" in profile:
        findings.append((FAIL, f"AAC profile is {profile} - players decode AAC-LC only"))
    findings.append(
        (WARN, "raw ADTS .aac streams are unreliable on players - remux into .m4a: "
               "ffmpeg -i in -c copy -bsf:a aac_adtstoasc out.m4a")
    )
    findings.extend(_check_rate_and_channels(audio, lossless=False))
    return findings


def collect_files(target: str) -> list[str]:
    if os.path.isfile(target):
        return [target]
    collected = []
    for root, _, names in os.walk(target):
        for name in names:
            if os.path.splitext(name)[1].lower() in AUDIO_EXTENSIONS:
                collected.append(os.path.join(root, name))
    return sorted(collected)


def main():
    parser = argparse.ArgumentParser(
        description="Check audio files for hardware DJ player (CDJ/XDJ) compatibility."
    )
    parser.add_argument("target", help="Audio file or directory to scan", type=str)
    parser.add_argument(
        "--all", action="store_true", help="Also list files that pass every check"
    )
    args = parser.parse_args()

    if shutil.which("ffprobe") is None:
        print("ffprobe not found - install ffmpeg first (see README).")
        sys.exit(2)

    files = collect_files(args.target)
    if not files:
        print("No audio files found.")
        sys.exit(0)

    counts = {FAIL: 0, WARN: 0, "OK": 0}
    for filepath in files:
        findings = check_file(filepath)
        worst = FAIL if any(l == FAIL for l, _ in findings) else (
            WARN if findings else "OK"
        )
        counts[worst] += 1
        if worst == "OK" and not args.all:
            continue
        print(f"[{worst}] {filepath}")
        for level, message in findings:
            print(f"       {level}: {message}")

    print(
        f"\nScanned {len(files)} file(s): "
        f"{counts['OK']} ok, {counts[WARN]} warning(s), {counts[FAIL]} failing"
    )
    sys.exit(1 if counts[FAIL] else 0)


if __name__ == "__main__":
    main()
