"""Module for downloading a track's audio from SoundCloud, given a permalink URL
found by soundcloud_search.py. Uses the progressive (plain HTTP mp3) stream -
the same one SoundCloud's own web player streams from for normal playback."""
import os

import requests

from src.file_metadata import FILE_EXTENSION_MP3
from src.soundcloud_search import HEADERS, RESOLVE_URL, get_client_id


class NoProgressiveStreamAvailableError(Exception):
    """Exception raised when a SoundCloud track has no progressive stream
    available (HLS-only or fully playback-restricted tracks)."""


def get_soundcloud_track_info(track_url: str) -> dict:
    """Fetch a track's metadata without downloading it.

    Returns a dict with 'artist', 'track' and 'duration' (seconds). SoundCloud
    titles frequently embed the artist as 'Artist - Track'; when they do not,
    the uploader name is used as the artist.
    """
    client_id = get_client_id()
    track = _resolve_track(track_url, client_id)

    title = (track.get("title") or "").strip()
    uploader = (track.get("user") or {}).get("username", "").strip()
    if " - " in title:
        artist, track_name = title.split(" - ", 1)
    else:
        artist, track_name = uploader, title

    return {
        "artist": artist.strip(),
        "track": track_name.strip(),
        "duration": int((track.get("duration") or 0) / 1000),
    }


def get_audio_from_soundcloud(track_url: str, output_dir: str, filename: str) -> str:
    """Download a track's audio from SoundCloud. Returns the final filepath,
    already in mp3 format - unlike YouTube, no separate conversion step is
    needed afterwards."""
    if not filename.endswith(FILE_EXTENSION_MP3):
        filename += FILE_EXTENSION_MP3

    print(f"\nDownloading '{filename.rstrip(FILE_EXTENSION_MP3)}' from SoundCloud")

    client_id = get_client_id()
    track = _resolve_track(track_url, client_id)
    stream_url = _get_progressive_stream_url(track, client_id)

    output_filepath = os.path.join(output_dir, filename)
    with requests.get(stream_url, headers=HEADERS, timeout=30, stream=True) as response:
        response.raise_for_status()
        with open(output_filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 256):
                f.write(chunk)

    return output_filepath


def _resolve_track(track_url: str, client_id: str) -> dict:
    response = requests.get(
        RESOLVE_URL, params={"url": track_url, "client_id": client_id}, headers=HEADERS, timeout=15
    )
    response.raise_for_status()
    return response.json()


def _get_progressive_stream_url(track: dict, client_id: str) -> str:
    transcodings = track.get("media", {}).get("transcodings", [])
    progressive = next(
        (t for t in transcodings if t.get("format", {}).get("protocol") == "progressive"), None
    )
    if not progressive:
        raise NoProgressiveStreamAvailableError(
            f"No progressive stream available for {track.get('permalink_url')}"
        )
    response = requests.get(
        progressive["url"], params={"client_id": client_id}, headers=HEADERS, timeout=15
    )
    response.raise_for_status()
    return response.json()["url"]
