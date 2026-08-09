"""Module for handling SoundCloud downloads via yt-dlp."""
import os
import subprocess

from yt_dlp import YoutubeDL

from src.file_metadata import FILE_EXTENSION_MP3

# SoundCloud serves public tracks as 128 kbps MP3 (progressive or HLS) and
# occasionally in other codecs (e.g. Opus). Prefer MP3, which every player
# supports and which needs no transcoding; anything else is converted to MP3.
AUDIO_FORMAT_PREFERENCE = "bestaudio[ext=mp3]/bestaudio"

FALLBACK_MP3_BITRATE = "192k"


def get_soundcloud_track_info(soundcloud_url: str) -> dict:
    """Fetch track metadata without downloading.

    Returns a dict with 'artist', 'track' and 'duration' (seconds). SoundCloud
    titles frequently embed the artist as 'Artist - Track'; when they do not,
    the uploader name is used as the artist.
    """
    with YoutubeDL({"quiet": True, "noplaylist": True}) as ydl:
        info = ydl.extract_info(soundcloud_url, download=False)

    title = (info.get("title") or "").strip()
    uploader = (info.get("uploader") or "").strip()
    if " - " in title:
        artist, track = title.split(" - ", 1)
    else:
        artist, track = uploader, title

    return {
        "artist": artist.strip(),
        "track": track.strip(),
        "duration": int(info.get("duration") or 0),
    }


def get_audio_from_soundcloud(
    soundcloud_url: str, output_dir: str, filename: str
) -> str:
    """Download a SoundCloud track's audio into output_dir as '<filename>.mp3'.

    MP3 sources are saved as-is (no transcoding); other codecs are converted
    to MP3. Returns the path of the downloaded file.
    """
    print(f"\nDownloading '{filename}'")
    options = {
        "quiet": True,
        "noprogress": True,
        "noplaylist": True,
        "format": AUDIO_FORMAT_PREFERENCE,
        "outtmpl": os.path.join(output_dir, filename + ".%(ext)s"),
    }
    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(soundcloud_url, download=True)
        output_filepath = ydl.prepare_filename(info)

    if not output_filepath.endswith(FILE_EXTENSION_MP3):
        output_filepath = _convert_to_mp3(output_filepath)

    return output_filepath


def _convert_to_mp3(input_filepath: str) -> str:
    """Convert an audio file in a non-MP3 codec (e.g. Opus) to MP3, so the
    result plays on hardware DJ players."""
    mp3_filepath = os.path.splitext(input_filepath)[0] + FILE_EXTENSION_MP3
    subprocess.run(
        [
            _get_ffmpeg_exe(),
            "-v",
            "error",
            "-y",
            "-i",
            input_filepath,
            "-vn",
            "-codec:a",
            "libmp3lame",
            "-b:a",
            FALLBACK_MP3_BITRATE,
            mp3_filepath,
        ],
        check=True,
    )
    os.remove(input_filepath)
    return mp3_filepath


def _get_ffmpeg_exe() -> str:
    """Return the ffmpeg executable to use: prefer the binary bundled with
    moviepy's imageio-ffmpeg dependency, falling back to ffmpeg on PATH."""
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"
