"""Module for authenticating with Tidal (device-code OAuth flow, using
tidalapi's own built-in shared client credentials - no developer registration
needed, unlike Spotify) and exporting a playlist straight to the CSV shape
`data_handling.get_data_list_from_exportify_csv` expects."""
import os
from pathlib import Path
from typing import List, Optional

import tidalapi

from src.csv_handling import write_csv

TIDAL_CACHE_PATH = ".tidal_cache.json"

COLUMN_ARTIST_NAME = "Artist Name(s)"
COLUMN_TRACK_NAME = "Track Name"
COLUMN_TRACK_DURATION_MS = "Track Duration (ms)"
COLUMN_GENRES = "Genres"
COLUMN_TEMPO = "Tempo"
EXPORT_COLUMNS = [
    COLUMN_ARTIST_NAME,
    COLUMN_TRACK_NAME,
    COLUMN_TRACK_DURATION_MS,
    COLUMN_GENRES,
    COLUMN_TEMPO,
]


def start_login() -> tidalapi.session.LinkLogin:
    """Start the device-code login flow: returns the info needed to show the
    user (verification_uri_complete + user_code), who completes login in
    another tab/device."""
    session = tidalapi.Session()
    return session.get_link_login()


def try_complete_login(link_login: tidalapi.session.LinkLogin) -> Optional[tidalapi.Session]:
    """Attempt to exchange the device code for a session, once the user has
    (hopefully) completed the browser step. Returns None if they haven't
    finished yet (caller should retry), or a ready-to-use session on success.
    A fresh Session is fine here (not the one from start_login) - the device
    code itself, not any session-local state, is what the exchange needs."""
    session = tidalapi.Session()
    try:
        success = session.process_link_login(link_login, until_expiry=False)
    except TimeoutError:
        return None
    if not success:
        return None
    session.save_session_to_file(Path(TIDAL_CACHE_PATH))
    return session


def get_cached_session() -> Optional[tidalapi.Session]:
    """Reuse a previously cached session, if one is on disk and still valid,
    so restarting the app doesn't force the user to log in again. Any failure
    (missing/invalid cache, network issue) just means falling back to the
    login flow, same graceful-degradation approach as the other sources."""
    if not os.path.exists(TIDAL_CACHE_PATH):
        return None
    session = tidalapi.Session()
    try:
        session.load_session_from_file(Path(TIDAL_CACHE_PATH))
        if not session.check_login():
            return None
    except Exception:
        return None
    return session


def logout() -> None:
    """Delete the cached session so the next login starts fresh."""
    try:
        os.remove(TIDAL_CACHE_PATH)
    except FileNotFoundError:
        pass


def list_user_playlists(session: tidalapi.Session) -> List[dict]:
    """List the logged-in user's own playlists."""
    if not isinstance(session.user, tidalapi.LoggedInUser):
        raise RuntimeError("Tidal session isn't fully logged in")
    playlists = session.user.playlists()
    results = []
    for p in playlists:
        try:
            image_url = p.image(320)
        except AttributeError:
            image_url = None
        results.append({"id": p.id, "name": p.name or "", "image_url": image_url})
    return results


def export_playlist_to_csv(session: tidalapi.Session, playlist_id: str, output_path: str) -> str:
    """Fetch a Tidal playlist's tracks and write them to a CSV shaped like an
    Exportify export, so it can be fed straight into
    `get_data_list_from_exportify_csv` exactly like the other sources.

    Genres/Tempo are left blank for consistency with the other export
    modules, even though Tidal's Track objects do expose native `bpm`/`key`
    fields - those aren't reliably populated across the catalog, so the
    existing local tempo estimation (post-download) stays the single source
    of truth rather than mixing in a sometimes-present value here."""
    playlist = session.playlist(playlist_id)
    tracks = playlist.tracks()

    rows = []
    for track in tracks:
        if track.duration is None:
            continue
        artist_names = ", ".join(artist.name for artist in (track.artists or []) if artist.name)
        rows.append(
            {
                COLUMN_ARTIST_NAME: artist_names,
                COLUMN_TRACK_NAME: track.title or "",
                COLUMN_TRACK_DURATION_MS: track.duration * 1000,
                COLUMN_GENRES: "",
                COLUMN_TEMPO: "",
            }
        )

    write_csv(output_path, rows, EXPORT_COLUMNS)
    return output_path
