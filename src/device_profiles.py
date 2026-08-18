"""Known audio format/quality ceilings for DJ hardware that plays files
straight off a USB stick (standalone CDJ/XDJ players and the rekordbox
library format itself).

DDJ controllers are intentionally not modeled here: they have no onboard
file reader, so whatever format plays is whatever software (rekordbox/
Serato) running on the connected laptop supports - there's no DDJ-specific
ceiling to target.

Only ``max_mp3_kbps`` is wired into the conversion pipeline today, since
output is MP3-only. The other fields describe what each device actually
supports and are here so a future multi-format pipeline change can read
them directly instead of re-deriving this table.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceProfile:
    formats: tuple[str, ...]
    max_mp3_kbps: int
    max_sample_rate_hz: int | None  # None = no device ceiling, passthrough from source
    max_bit_depth: int | None  # applies to WAV/AIFF; None = not applicable/no ceiling


DEVICE_PROFILES: dict[str, DeviceProfile] = {
    "CDJ-3000 / XDJ-XZ (current gen)": DeviceProfile(
        formats=("mp3", "wav", "aiff", "flac", "alac", "aac"),
        max_mp3_kbps=320,
        max_sample_rate_hz=96000,
        max_bit_depth=24,
    ),
    "CDJ-2000NXS2 / XDJ-1000MK2": DeviceProfile(
        formats=("mp3", "wav", "aiff", "aac"),
        max_mp3_kbps=320,
        max_sample_rate_hz=96000,
        max_bit_depth=24,
    ),
    "CDJ-2000 / CDJ-900 (legacy)": DeviceProfile(
        formats=("mp3", "wav", "aiff"),
        max_mp3_kbps=320,
        max_sample_rate_hz=48000,
        max_bit_depth=16,
    ),
    "rekordbox library (software only)": DeviceProfile(
        formats=("mp3", "wav", "aiff", "flac", "alac", "aac"),
        max_mp3_kbps=320,
        max_sample_rate_hz=None,
        max_bit_depth=None,
    ),
}
