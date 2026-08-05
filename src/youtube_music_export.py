"""Module for authenticating with YouTube Music via a redirect-based OAuth flow
(same shape as spotify_export.py's, unlike ytmusicapi's own built-in OAuth module
which only implements the device flow meant for TVs/limited-input devices) and
exporting a playlist straight to the CSV shape
`data_handling.get_data_list_from_exportify_csv` expects."""
import os
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv
from ytmusicapi import YTMusic
from ytmusicapi.auth.oauth.credentials import OAuthCredentials
from ytmusicapi.auth.oauth.token import RefreshingToken

from src.csv_handling import write_csv

load_dotenv()

# Requires a Google Cloud OAuth client of type "Web application" (not "TVs and
# Limited Input devices" - that type doesn't support redirect URIs at all), with
# the YouTube Data API v3 enabled and this app's URL registered as a redirect URI.
# Configured via .env (see .env.example) rather than hardcoded - unlike Spotify's
# PKCE client_id, this client_secret is a real credential, so keeping it out of
# source/version control matters here even though this client type doesn't treat
# it as strictly confidential the way a server-side web app's secret would be.
YOUTUBE_MUSIC_CLIENT_ID = os.getenv("YOUTUBE_MUSIC_CLIENT_ID", "")
YOUTUBE_MUSIC_CLIENT_SECRET = os.getenv("YOUTUBE_MUSIC_CLIENT_SECRET", "")

# Must also be registered as a Redirect URI on the Google Cloud OAuth client, and
# match the address Streamlit actually serves the app on. Try the IP literal
# first (matches Spotify's requirement); if Google's console rejects it, use
# "http://localhost:8501" instead - Google's validation rules differ from
# Spotify's here and accept either depending on client configuration.
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://127.0.0.1:8501")
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_OAUTH_SCOPE = "https://www.googleapis.com/auth/youtube"

YOUTUBE_MUSIC_CACHE_PATH = ".ytmusic_cache.json"

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


class YouTubeMusicNotConfiguredError(Exception):
    """Exception raised when YOUTUBE_MUSIC_CLIENT_ID/SECRET haven't been filled in."""


class YouTubeMusicLoginError(Exception):
    """Exception raised when the OAuth code exchange fails."""


def _get_credentials() -> OAuthCredentials:
    if not YOUTUBE_MUSIC_CLIENT_ID or not YOUTUBE_MUSIC_CLIENT_SECRET:
        raise YouTubeMusicNotConfiguredError(
            "YouTube Music login isn't set up yet - add YOUTUBE_MUSIC_CLIENT_ID and "
            "YOUTUBE_MUSIC_CLIENT_SECRET in src/youtube_music_export.py."
        )
    # Reused for token refresh below (Google's refresh flow is identical no matter
    # how the original code/token was obtained), even though this credentials
    # class's own get_code()/token_from_code() (device flow) go unused here.
    return OAuthCredentials(client_id=YOUTUBE_MUSIC_CLIENT_ID, client_secret=YOUTUBE_MUSIC_CLIENT_SECRET)


def build_login_url() -> str:
    """Build the Google OAuth consent URL for the redirect-based login flow -
    same shape as spotify_export.build_login_url. `access_type=offline` +
    `prompt=consent` are both required to reliably get a refresh_token back on
    every login (Google can otherwise skip re-issuing one on repeat consents)."""
    _get_credentials()  # raises YouTubeMusicNotConfiguredError early if unset
    params = {
        "client_id": YOUTUBE_MUSIC_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": GOOGLE_OAUTH_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": "ytmusic",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def complete_login(code: str) -> YTMusic:
    """Finish a login started by `build_login_url`, using the `code` query param
    Google's redirect came back with."""
    credentials = _get_credentials()
    response = requests.post(
        GOOGLE_TOKEN_URL,
        data={
            "client_id": YOUTUBE_MUSIC_CLIENT_ID,
            "client_secret": YOUTUBE_MUSIC_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": GOOGLE_REDIRECT_URI,
        },
        timeout=15,
    )
    response.raise_for_status()
    raw_token = response.json()

    if "refresh_token" not in raw_token:
        raise YouTubeMusicLoginError(
            "Google didn't return a refresh token - log out and try logging in again."
        )

    token = RefreshingToken(
        credentials=credentials,
        access_token=raw_token["access_token"],
        refresh_token=raw_token["refresh_token"],
        scope=raw_token.get("scope", GOOGLE_OAUTH_SCOPE),
        token_type=raw_token.get("token_type", "Bearer"),
        expires_in=raw_token["expires_in"],
    )
    token.update(raw_token)
    token.local_cache = Path(YOUTUBE_MUSIC_CACHE_PATH)
    return YTMusic(auth=dict(token.as_dict()), oauth_credentials=credentials)


def get_cached_ytmusic_client() -> Optional[YTMusic]:
    """Reuse a previously cached token, if one is on disk, so restarting the app
    doesn't force the user to log in again. Any failure (missing/invalid cache,
    network issue) just means falling back to showing the login flow, same
    graceful-degradation approach as spotify_export.get_cached_spotify_client."""
    if not YOUTUBE_MUSIC_CLIENT_ID or not os.path.exists(YOUTUBE_MUSIC_CACHE_PATH):
        return None
    try:
        return YTMusic(auth=YOUTUBE_MUSIC_CACHE_PATH, oauth_credentials=_get_credentials())
    except Exception:
        return None


def logout() -> None:
    """Delete the cached token so the next login starts fresh."""
    try:
        os.remove(YOUTUBE_MUSIC_CACHE_PATH)
    except FileNotFoundError:
        pass


def list_user_playlists(yt: YTMusic) -> List[dict]:
    """List the logged-in user's own library playlists."""
    playlists = yt.get_library_playlists(limit=None)
    return [
        {
            "id": p["playlistId"],
            "name": p.get("title") or "",
            "image_url": (p.get("thumbnails") or [{}])[-1].get("url"),
        }
        for p in playlists
        if p.get("playlistId")
    ]


def export_playlist_to_csv(yt: YTMusic, playlist_id: str, output_path: str) -> str:
    """Fetch a YouTube Music playlist's tracks and write them to a CSV shaped
    like an Exportify export, so it can be fed straight into
    `get_data_list_from_exportify_csv` exactly like the Spotify export path."""
    playlist = yt.get_playlist(playlist_id, limit=None)

    rows = []
    for track in playlist.get("tracks", []):
        duration_seconds = track.get("duration_seconds")
        if not track.get("videoId") or duration_seconds is None:
            continue
        artist_names = ", ".join(a["name"] for a in track.get("artists", []) if a.get("name"))
        rows.append(
            {
                COLUMN_ARTIST_NAME: artist_names,
                COLUMN_TRACK_NAME: track.get("title", ""),
                COLUMN_TRACK_DURATION_MS: duration_seconds * 1000,
                COLUMN_GENRES: "",
                COLUMN_TEMPO: "",
            }
        )

    write_csv(output_path, rows, EXPORT_COLUMNS)
    return output_path
