"""Module for exporting a Spotify playlist straight to the CSV shape
`data_handling.get_data_list_from_exportify_csv` already expects, so the app
doesn't need a separate trip through exportify.net."""
import os
import re
from typing import Dict, List, Optional

import spotipy
from spotipy.oauth2 import SpotifyPKCE

from src.csv_handling import write_csv

# Public by design: PKCE client IDs aren't secrets (there's no client secret to leak),
# so - same as Exportify's own hardcoded ID - everyone running this app shares this ID
# and each logs in with their own Spotify account against it.
SPOTIFY_CLIENT_ID = "650d6ba75e0343498dd4afe05a90317e"

SPOTIFY_REDIRECT_URI_CLI = "http://127.0.0.1:8080/callback"
# Must also be registered as a Redirect URI on the Spotify app, and match the
# address Streamlit actually serves the app on (its default local port). Spotify
# requires the loopback IP literal here rather than "localhost" - the hostname
# isn't accepted as a secure redirect target.
SPOTIFY_REDIRECT_URI_APP = "http://127.0.0.1:8501"
SPOTIFY_SCOPE = "playlist-read-private playlist-read-collaborative"
SPOTIFY_CACHE_PATH = ".spotify_cache"

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

PLAYLIST_ID_RE = re.compile(r"playlist[/:]([A-Za-z0-9]+)")


def extract_playlist_id(playlist_url_or_id: str) -> str:
    """Pull a playlist ID out of a Spotify URL or URI, or accept a raw ID directly."""
    match = PLAYLIST_ID_RE.search(playlist_url_or_id)
    return match.group(1) if match else playlist_url_or_id


def get_spotify_client(client_id: str) -> spotipy.Spotify:
    """Authenticate via OAuth PKCE and return a ready-to-use Spotify client.
    Interactive: opens a browser and prompts for the redirect URL on first use
    (meant for one-off CLI/script use, not the Streamlit app)."""
    auth_manager = SpotifyPKCE(
        client_id=client_id,
        redirect_uri=SPOTIFY_REDIRECT_URI_CLI,
        scope=SPOTIFY_SCOPE,
        cache_path=SPOTIFY_CACHE_PATH,
    )
    return spotipy.Spotify(auth_manager=auth_manager)


# Holds the PKCE auth manager between "show the user a login link" and "Spotify
# redirects back with a code". Spotify's redirect can land in a different browser
# tab/session than the one that started the login, so this can't live in Streamlit's
# per-session `st.session_state` - it's a process-wide global instead, which is fine
# since this is a single-user local app (one login in flight at a time).
_pending_auth_manager: Optional[SpotifyPKCE] = None


def _build_app_auth_manager(client_id: str) -> SpotifyPKCE:
    return SpotifyPKCE(
        client_id=client_id,
        redirect_uri=SPOTIFY_REDIRECT_URI_APP,
        scope=SPOTIFY_SCOPE,
        cache_path=SPOTIFY_CACHE_PATH,
        open_browser=False,
    )


def build_login_url(client_id: str) -> str:
    """Start a login from the Streamlit app: create the PKCE auth manager and
    return the URL to send the user's browser to."""
    global _pending_auth_manager
    _pending_auth_manager = _build_app_auth_manager(client_id)
    return _pending_auth_manager.get_authorize_url()


def complete_login(code: str) -> spotipy.Spotify:
    """Finish a login started by `build_login_url`, using the `code` query param
    Spotify's redirect came back with."""
    if _pending_auth_manager is None:
        raise RuntimeError("No Spotify login in progress")
    _pending_auth_manager.get_access_token(code, check_cache=False)
    return spotipy.Spotify(auth_manager=_pending_auth_manager)


def logout() -> None:
    """Delete the cached token so the next login starts fresh, rather than
    silently picking the old session back up via `get_cached_spotify_client`."""
    try:
        os.remove(SPOTIFY_CACHE_PATH)
    except FileNotFoundError:
        pass


def get_cached_spotify_client(client_id: str) -> Optional[spotipy.Spotify]:
    """Reuse a previously cached token, if one is on disk and still valid, so
    restarting the app doesn't force the user to log in again."""
    auth_manager = _build_app_auth_manager(client_id)
    token_info = auth_manager.validate_token(auth_manager.cache_handler.get_cached_token())
    return spotipy.Spotify(auth_manager=auth_manager) if token_info else None


def list_user_playlists(sp: spotipy.Spotify) -> List[dict]:
    """List the logged-in user's own playlists (not ones they merely follow or
    collaborate on - fetching those often 403s anyway), so the UI can offer a
    picker instead of requiring a pasted playlist URL (matching Exportify's flow)."""
    current_user_id = sp.current_user()["id"]
    playlists_by_id: Dict[str, dict] = {}
    results = sp.current_user_playlists()
    while results:
        for p in results["items"]:
            # Deleted/inaccessible playlists surface as stub entries missing most fields.
            if not p or not p.get("id"):
                continue
            if (p.get("owner") or {}).get("id") != current_user_id:
                continue
            # The API can list the same playlist twice (e.g. owned + collaborated on),
            # so key by ID rather than appending, to keep the UI list unique.
            playlists_by_id[p["id"]] = {
                "id": p["id"],
                "name": p.get("name") or "",
                "image_url": (p.get("images") or [{}])[0].get("url"),
            }
        results = sp.next(results) if results.get("next") else None
    return list(playlists_by_id.values())


def _fetch_all_tracks(sp: spotipy.Spotify, playlist_id: str) -> List[dict]:
    """Page through every track in the playlist.

    Deliberately doesn't use a `fields=` projection: depending on the app/API
    version, Spotify wraps each entry's track data under either a "track" key
    (the documented shape) or an "item" key (seen on newer apps) - filtering by
    field name up front risks silently asking for a field that doesn't exist and
    getting nothing back, exactly like the "item" vs "track" bug found here.
    """
    tracks: List[dict] = []
    results = sp.playlist_items(playlist_id, additional_types=["track"])
    while results:
        for entry in results["items"]:
            track = entry.get("track") or entry.get("item")
            if track and track.get("id"):
                tracks.append(track)
        results = sp.next(results) if results.get("next") else None
    return tracks


def _fetch_artist_genres(sp: spotipy.Spotify, artist_ids: List[str]) -> Dict[str, List[str]]:
    """Batch-fetch genres per artist (the artists endpoint takes up to 50 IDs per call).
    Some apps get a 403 here depending on Spotify's current access tier, so - like
    tempo below - a failure just means every artist falls back to no genres instead
    of failing the whole export."""
    genres_by_id: Dict[str, List[str]] = {}
    unique_ids = list(dict.fromkeys(artist_ids))
    try:
        for i in range(0, len(unique_ids), 50):
            batch = unique_ids[i : i + 50]
            for artist in sp.artists(batch)["artists"]:
                genres_by_id[artist["id"]] = artist.get("genres", [])
    except spotipy.SpotifyException:
        pass
    return genres_by_id


def _fetch_tempos(sp: spotipy.Spotify, track_ids: List[str]) -> Dict[str, int]:
    """Batch-fetch tempo per track. Spotify's audio-features endpoint is gated behind
    extended API access for apps created after Nov 2024, so a 403 here just means
    every track falls back to an empty Tempo column instead of failing the export."""
    tempo_by_id: Dict[str, int] = {}
    try:
        for i in range(0, len(track_ids), 100):
            batch = track_ids[i : i + 100]
            for features in sp.audio_features(batch):
                if features:
                    tempo_by_id[features["id"]] = round(features["tempo"])
    except spotipy.SpotifyException:
        pass
    return tempo_by_id


def export_playlist_to_csv(sp: spotipy.Spotify, playlist_url_or_id: str, output_path: str) -> str:
    """Fetch a Spotify playlist's tracks and write them to a CSV shaped like an Exportify
    export, so it can be fed straight into `get_data_list_from_exportify_csv`.

    Takes an already-authenticated client so the UI can log in once, list playlists,
    then export a chosen one without re-running the OAuth flow."""
    playlist_id = extract_playlist_id(playlist_url_or_id)

    tracks = _fetch_all_tracks(sp, playlist_id)
    artist_ids = [artist["id"] for track in tracks for artist in track["artists"]]
    genres_by_artist = _fetch_artist_genres(sp, artist_ids)
    tempo_by_track = _fetch_tempos(sp, [track["id"] for track in tracks])

    rows = []
    for track in tracks:
        artist_names = ", ".join(artist["name"] for artist in track["artists"])
        genres = sorted(
            {genre for artist in track["artists"] for genre in genres_by_artist.get(artist["id"], [])}
        )
        rows.append(
            {
                COLUMN_ARTIST_NAME: artist_names,
                COLUMN_TRACK_NAME: track["name"],
                COLUMN_TRACK_DURATION_MS: track["duration_ms"],
                COLUMN_GENRES: ", ".join(genres),
                COLUMN_TEMPO: tempo_by_track.get(track["id"], ""),
            }
        )

    write_csv(output_path, rows, EXPORT_COLUMNS)
    return output_path
