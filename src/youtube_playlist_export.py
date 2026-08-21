"""Module for exporting a public/unlisted YouTube (or YouTube Music) playlist
straight to CSV from a pasted URL - no login needed, unlike the Spotify/Tidal
sources. Uses unauthenticated ytmusicapi (already a dependency for matching),
which resolves regular YouTube playlists (PL...), YouTube Music playlists and
album share links (OLAK5uy_...) alike.

Every entry already carries its videoId, so the CSV is written in the
"with IDs" shape (same header as template_with_ids.csv) - the app's matching
stage is skipped entirely and rows arrive pre-matched. Duration is therefore
written directly in seconds: `get_data_list_from_csv_with_ids` does no ms->s
normalization."""
import re
from typing import Optional, Tuple

from ytmusicapi import YTMusic

from src.csv_handling import write_csv
from src.data_handling import (
    COLUMN_ARTIST_NAME,
    COLUMN_GENRES,
    COLUMN_TEMPO,
    COLUMN_TRACK_DURATION,
    COLUMN_TRACK_NAME,
    COLUMN_YOUTUBE_ID,
)

EXPORT_COLUMNS = [
    COLUMN_ARTIST_NAME,
    COLUMN_TRACK_NAME,
    COLUMN_TRACK_DURATION,
    COLUMN_GENRES,
    COLUMN_TEMPO,
    COLUMN_YOUTUBE_ID,
]

YOUTUBE_PLAYLIST_URL_RE = re.compile(r"[?&]list=([A-Za-z0-9_-]+)")
YOUTUBE_PLAYLIST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{12,}$")


class YoutubePlaylistUnavailableError(Exception):
    """The playlist couldn't be fetched (private, deleted, or not a playlist)."""


def extract_playlist_id(text: str) -> Optional[str]:
    """Pull a playlist ID out of a pasted YouTube/YouTube Music URL (any URL
    with a `list=` param, including watch?v=...&list=...), or accept a raw ID
    directly. Strips the "VL" prefix from share links - ytmusicapi prepends it
    itself."""
    text = (text or "").strip()
    if not text:
        return None
    match = YOUTUBE_PLAYLIST_URL_RE.search(text)
    playlist_id = match.group(1) if match else (text if YOUTUBE_PLAYLIST_ID_RE.match(text) else None)
    if playlist_id and playlist_id.startswith("VL"):
        playlist_id = playlist_id[2:]
    return playlist_id


def export_playlist_to_csv(playlist_id: str, output_path: str) -> Tuple[str, int]:
    """Fetch a playlist's entries and write them to a with-IDs CSV. Returns
    (playlist title, number of skipped entries) - unlike the other sources
    there's no picker supplying a name, so the title comes back from here to
    name the CSV (and thus the download folder).

    Unavailable entries (deleted/private videos come back with videoId None)
    are skipped rather than left Pending: auto-matching them from a
    possibly-wrong title would silently download the wrong thing."""
    try:
        playlist = YTMusic().get_playlist(playlist_id, limit=None)
    except Exception as exc:
        # ytmusicapi surfaces private/nonexistent playlists as raw KeyErrors
        # from its response navigation, so any failure here gets one message.
        raise YoutubePlaylistUnavailableError(
            "Couldn't fetch that playlist - it may be private, deleted, or not a playlist link."
        ) from exc

    rows = []
    skipped = 0
    for track in playlist.get("tracks") or []:
        video_id = track.get("videoId")
        duration_seconds = track.get("duration_seconds")
        if not video_id or duration_seconds is None:
            skipped += 1
            continue
        artist_names = ", ".join(
            artist["name"] for artist in (track.get("artists") or []) if artist.get("name")
        )
        rows.append(
            {
                COLUMN_ARTIST_NAME: artist_names,
                COLUMN_TRACK_NAME: track.get("title") or "",
                COLUMN_TRACK_DURATION: duration_seconds,
                COLUMN_GENRES: "",
                COLUMN_TEMPO: "",
                COLUMN_YOUTUBE_ID: video_id,
            }
        )

    write_csv(output_path, rows, EXPORT_COLUMNS)
    return playlist.get("title") or "YouTube Playlist", skipped
