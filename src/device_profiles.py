"""Known audio format/quality ceilings for DJ hardware that plays files
straight off a USB stick (standalone CDJ/XDJ players).

These two tiers - and the device models named in each - come directly from
check_hardware_compat.py's own comments: that script already distinguishes
exactly these two generations (FLAC/ALAC and hi-res sample rates play on one,
not the other) without a formal table. This module gives that split a name so
a device picker (or any other pipeline code) can reference it directly instead
of re-deriving the same facts.

DDJ controllers are intentionally not modeled here: they have no onboard
file reader, so whatever format plays is whatever software (rekordbox/
Serato) running on the connected laptop supports - there's no DDJ-specific
ceiling to target.

Only ``max_mp3_kbps`` is wired into the conversion pipeline today, since
output is MP3-only. The other fields describe what each device actually
supports and are read directly by check_hardware_compat.py's per-device
checks, and are here for a future multi-format pipeline change too.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceProfile:
    name: str
    formats: tuple[str, ...]
    max_mp3_kbps: int
    max_sample_rate_hz: int | None  # None = no device ceiling, passthrough from source
    max_bit_depth: int | None  # applies to WAV/AIFF; None = not applicable/no ceiling


DEVICE_PROFILES: dict[str, DeviceProfile] = {
    "2016+ players (XDJ-1000MK2, NXS2, CDJ-3000, XDJ-AZ)": DeviceProfile(
        name="2016+ players (XDJ-1000MK2, NXS2, CDJ-3000, XDJ-AZ)",
        formats=("mp3", "wav", "aiff", "flac", "alac", "aac"),
        max_mp3_kbps=320,
        max_sample_rate_hz=96000,
        max_bit_depth=24,
    ),
    "Legacy players (CDJ-850, CDJ-900, CDJ-2000, XDJ-1000 mk1)": DeviceProfile(
        name="Legacy players (CDJ-850, CDJ-900, CDJ-2000, XDJ-1000 mk1)",
        formats=("mp3", "wav", "aiff", "aac"),
        max_mp3_kbps=320,
        max_sample_rate_hz=48000,
        max_bit_depth=24,
    ),
}
