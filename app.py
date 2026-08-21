"""Streamlit UI wrapping the music-downloader pipeline:
Exportify CSV -> matched Youtube IDs -> downloaded audio -> tagged MP3s.

Every track is tracked as a row with a 'State' column that's updated live
as it moves through matching, downloading (with bot-detection retries) and
MP3 conversion.
"""
import html
import os
import random
import re
import tempfile
import time
from collections import Counter
from pathlib import Path

import requests
import spotipy
import streamlit as st
import tidalapi
from pytubefix.exceptions import BotDetection

from check_hardware_compat import FAIL as HARDWARE_COMPAT_FAIL
from check_hardware_compat import check_file as check_hardware_compat
from convert_tracks_to_mp3 import convert_to_mp3
from src.csv_handling import read_csv, write_csv
from src.data_handling import (
    COLUMN_ARTIST_NAME,
    COLUMN_BIT_RATE,
    COLUMN_GENRES,
    COLUMN_SOUNDCLOUD_URL,
    COLUMN_TEMPO,
    COLUMN_TRACK_DURATION,
    COLUMN_TRACK_NAME,
    COLUMN_YOUTUBE_ID,
    get_data_list_from_csv_with_ids,
    get_data_list_from_exportify_csv,
    get_song_filename,
    get_song_search_string,
    get_youtube_url,
    sanitize_filename,
)
from src.device_profiles import DEVICE_PROFILES
from src.file_handling import scan_directory_for_audio_files
from src.file_metadata import (
    FILE_EXTENSION_MP3,
    FILE_EXTENSION_MP4,
    SUPPORTED_FORMATS,
    get_file_bit_rate_kbps,
    prepare_metadata_tags,
    set_file_metadata_tags,
)
from src.soundcloud_download import get_audio_from_soundcloud
from src.soundcloud_search import (
    NoMatchingSoundcloudTrackFoundError,
    find_best_matching_soundcloud_track,
    search_soundcloud_tracks,
)
from src.spotify_export import SPOTIFY_CLIENT_ID
from src.spotify_export import build_login_url as build_spotify_login_url
from src.spotify_export import complete_login as complete_spotify_login
from src.spotify_export import export_playlist_to_csv as export_spotify_playlist_to_csv
from src.spotify_export import get_cached_spotify_client
from src.spotify_export import list_user_playlists as list_spotify_playlists
from src.spotify_export import logout as spotify_logout
from src.tempo_estimation import estimate_tempo
from src.tidal_export import export_playlist_to_csv as export_tidal_playlist_to_csv
from src.tidal_export import get_cached_session as get_cached_tidal_session
from src.tidal_export import list_user_playlists as list_tidal_playlists
from src.tidal_export import logout as tidal_logout
from src.tidal_export import start_login as start_tidal_login
from src.tidal_export import try_complete_login as try_complete_tidal_login
from src.youtube_download import get_audio_from_youtube
from src.youtube_music_search import (
    NoMatchingYoutubeMusicVideoFoundError,
    find_best_matching_youtube_music_video,
    get_youtube_music_search_results,
)
from src.youtube_playlist_export import YoutubePlaylistUnavailableError
from src.youtube_playlist_export import export_playlist_to_csv as export_youtube_playlist_to_csv
from src.youtube_playlist_export import extract_playlist_id as extract_youtube_playlist_id

# Covers HTTP errors from Spotify (SpotifyException), OAuth-specific failures
# (SpotifyOauthError - both share the SpotifyBaseException base), and raw
# network-level failures (timeouts, DNS/connection errors) that spotipy doesn't
# wrap itself. Used everywhere a Spotify API call could plausibly fail, so a
# network hiccup shows a clean message instead of crashing the whole app.
SPOTIFY_ERRORS = (requests.RequestException, spotipy.SpotifyBaseException)

# Same idea again, for Tidal: network failures plus every tidalapi-raised error
# (TidalAPIError is the common base for all of them).
TIDAL_ERRORS = (requests.RequestException, tidalapi.exceptions.TidalAPIError)

# And for the YouTube playlist source: network failures plus the module's own
# "couldn't fetch that playlist" error (which already wraps ytmusicapi's raw
# failure modes into a user-friendly message).
YOUTUBE_ERRORS = (requests.RequestException, YoutubePlaylistUnavailableError)

STATE_PENDING = "Pending"
STATE_MATCHED = "Matched"
STATE_NO_MATCH = "No match"
STATE_DOWNLOADING = "Downloading"
STATE_DOWNLOADED = "Downloaded"
STATE_RETRYING = "Retrying"
STATE_FAILED_BEFORE_RETRY = "Failed before retry"
STATE_FAILED = "Failed"
STATE_CONVERTING = "Converting"
STATE_CONVERTED = "Converted"
STATE_FAILED_CONVERTING = "Failed converting"

MAX_BOT_DETECTION_RETRIES = 3
RETRY_BACKOFF_BASE_SECONDS = 5

# Row key (not a CSV column - never added to display_columns) holding this
# track's check_hardware_compat.py findings for the selected target device.
ROW_KEY_HARDWARE_COMPAT_FINDINGS = "HardwareCompatFindings"

# (r, g, b) tint per state: gray=not started, blue=matched, amber=in progress/transient,
# green=success, red=terminal failure.
STATE_COLORS = {
    STATE_PENDING: (128, 128, 128),
    STATE_MATCHED: (33, 150, 243),
    STATE_NO_MATCH: (244, 67, 54),
    STATE_DOWNLOADING: (255, 152, 0),
    STATE_RETRYING: (255, 152, 0),
    STATE_FAILED_BEFORE_RETRY: (255, 152, 0),
    STATE_DOWNLOADED: (76, 175, 80),
    STATE_CONVERTING: (255, 152, 0),
    STATE_CONVERTED: (76, 175, 80),
    STATE_FAILED: (244, 67, 54),
    STATE_FAILED_CONVERTING: (244, 67, 54),
}

TRACK_CARD_STYLE = (
    "<style>"
    ".track-card { border: 1px solid rgba(128,128,128,0.25); border-radius: 8px; padding: 10px 14px; margin-bottom: 8px; }"
    ".track-card-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }"
    ".track-title { font-weight: 600; font-size: 0.95rem; }"
    ".track-artist { font-size: 0.85rem; opacity: 0.65; margin-left: 4px; }"
    ".track-actions { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }"
    ".state-badge { font-size: 0.72rem; font-weight: 600; padding: 2px 9px; border-radius: 999px; white-space: nowrap; }"
    ".compat-badge { font-size: 0.72rem; font-weight: 600; padding: 2px 9px; border-radius: 999px; "
    "white-space: nowrap; cursor: help; }"
    ".compat-badge.compat-warn { background-color: rgba(255,152,0,0.15); color: rgb(255,152,0); }"
    ".compat-badge.compat-fail { background-color: rgba(244,67,54,0.15); color: rgb(244,67,54); }"
    ".yt-link, .yt-link-disabled, .sc-link { display: inline-block; font-size: 0.78rem; font-weight: 600; "
    "padding: 6px 14px; border-radius: 6px; text-decoration: none; white-space: nowrap; border: none; }"
    ".yt-link { background-color: #FF0000; color: white; box-shadow: 0 1px 2px rgba(0,0,0,0.25); cursor: pointer; }"
    ".yt-link:hover { background-color: #cc0000; }"
    ".yt-link-disabled { background-color: rgba(128,128,128,0.18); color: rgba(128,128,128,0.6); cursor: not-allowed; }"
    ".sc-link { background-color: #FF5500; color: white; box-shadow: 0 1px 2px rgba(0,0,0,0.25); cursor: pointer; }"
    ".sc-link:hover { background-color: #cc4400; }"
    ".track-card-bottom { display: flex; justify-content: space-between; align-items: flex-end; margin-top: 8px; gap: 12px; }"
    ".track-annotations { font-size: 0.72rem; opacity: 0.55; white-space: nowrap; }"
    ".track-genres { display: flex; flex-wrap: wrap; gap: 4px; justify-content: flex-end; max-width: 70%; }"
    ".genre-tag { font-size: 0.68rem; padding: 1px 8px; border-radius: 999px; background-color: rgba(128,128,128,0.15); "
    "opacity: 0.85; white-space: nowrap; }"
    ".genre-summary { display: flex; flex-wrap: wrap; gap: 4px; justify-content: flex-end; align-items: center; "
    "padding-top: 8px; }"
    "</style>"
)

SPOTIFY_SIDEBAR_STYLE = (
    "<style>"
    ".spotify-login-link { display: inline-block; width: 100%; text-align: center; "
    "background-color: #1DB954; color: white; font-weight: 600; font-size: 0.85rem; "
    "padding: 8px 0; border-radius: 999px; text-decoration: none; margin-bottom: 12px; }"
    ".spotify-login-link:hover { background-color: #1ed760; }"
    ".playlist-row { display: flex; align-items: center; gap: 10px; padding: 6px 0; "
    "border-bottom: 1px solid rgba(128,128,128,0.15); }"
    ".playlist-row img { width: 36px; height: 36px; border-radius: 4px; object-fit: cover; flex-shrink: 0; }"
    ".playlist-row-placeholder { width: 36px; height: 36px; border-radius: 4px; flex-shrink: 0; "
    "background-color: rgba(128,128,128,0.2); }"
    ".playlist-row-name { font-size: 0.85rem; overflow: hidden; text-overflow: ellipsis; "
    "white-space: nowrap; flex: 1; }"
    "</style>"
)

# Small original glyphs evoking each service's mark (not a reproduction of the
# real trademarked artwork): Spotify's soundwave arcs, Tidal's diamond "T",
# YouTube's play triangle.
# Two variants each:
# - "glyph" is transparent-background, `currentColor` only - used on the active
#   tab, which already supplies the brand-colored background itself.
# - "badge" bakes in its own brand-colored shape (Spotify's circle, YouTube's
#   rounded rectangle, Tidal's rounded square) plus a white glyph - a
#   self-contained icon, used on inactive tabs sitting on a gray background.
SPOTIFY_LOGO_GLYPH_SVG = (
    '<svg width="18" height="18" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
    '<path d="M6 9.5C9 8 15 8 18 9.8" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round"/>'
    '<path d="M6.5 12.3C9.3 11 14.8 11 17.3 12.6" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linecap="round"/>'
    '<path d="M7 15C9.5 14 13.8 14 16 15.2" stroke="currentColor" stroke-width="1.4" fill="none" stroke-linecap="round"/>'
    "</svg>"
)
TIDAL_LOGO_GLYPH_SVG = (
    '<svg width="18" height="18" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
    '<rect x="6.26" y="8.38" width="3" height="3" fill="currentColor" transform="rotate(45 7.76 9.88)"/>'
    '<rect x="10.5" y="8.38" width="3" height="3" fill="currentColor" transform="rotate(45 12 9.88)"/>'
    '<rect x="14.74" y="8.38" width="3" height="3" fill="currentColor" transform="rotate(45 16.24 9.88)"/>'
    '<rect x="10.5" y="12.62" width="3" height="3" fill="currentColor" transform="rotate(45 12 14.12)"/>'
    "</svg>"
)

SPOTIFY_LOGO_BADGE_SVG = (
    '<svg width="22" height="22" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
    '<circle cx="12" cy="12" r="12" fill="#1DB954"/>'
    '<path d="M6 9.5C9 8 15 8 18 9.8" stroke="white" stroke-width="1.6" fill="none" stroke-linecap="round"/>'
    '<path d="M6.5 12.3C9.3 11 14.8 11 17.3 12.6" stroke="white" stroke-width="1.4" fill="none" stroke-linecap="round"/>'
    '<path d="M7 15C9.5 14 13.8 14 16 15.2" stroke="white" stroke-width="1.2" fill="none" stroke-linecap="round"/>'
    "</svg>"
)
TIDAL_LOGO_BADGE_SVG = (
    '<svg width="22" height="22" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
    '<rect x="1" y="1" width="22" height="22" rx="6" fill="#000000"/>'
    '<rect x="6.26" y="8.38" width="3" height="3" fill="white" transform="rotate(45 7.76 9.88)"/>'
    '<rect x="10.5" y="8.38" width="3" height="3" fill="white" transform="rotate(45 12 9.88)"/>'
    '<rect x="14.74" y="8.38" width="3" height="3" fill="white" transform="rotate(45 16.24 9.88)"/>'
    '<rect x="10.5" y="12.62" width="3" height="3" fill="white" transform="rotate(45 12 14.12)"/>'
    "</svg>"
)
YOUTUBE_LOGO_GLYPH_SVG = (
    '<svg width="18" height="18" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
    '<rect x="3" y="6.5" width="18" height="11" rx="3" stroke="currentColor" stroke-width="1.8" fill="none"/>'
    '<path d="M10.5 9.5L15 12L10.5 14.5Z" fill="currentColor"/>'
    "</svg>"
)
YOUTUBE_LOGO_BADGE_SVG = (
    '<svg width="22" height="22" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
    '<rect x="1" y="4.5" width="22" height="15" rx="4" fill="#FF0000"/>'
    '<path d="M9.8 8.8L15.5 12L9.8 15.2Z" fill="white"/>'
    "</svg>"
)

# (name, active-state glyph svg, inactive-state badge svg, brand color) for the
# playlist-source tab bar.
PLAYLIST_SOURCES = [
    ("Spotify", SPOTIFY_LOGO_GLYPH_SVG, SPOTIFY_LOGO_BADGE_SVG, "#1DB954"),
    ("Tidal", TIDAL_LOGO_GLYPH_SVG, TIDAL_LOGO_BADGE_SVG, "#000000"),
    ("YouTube", YOUTUBE_LOGO_GLYPH_SVG, YOUTUBE_LOGO_BADGE_SVG, "#FF0000"),
]

# Zero gap between the three source-tab columns, so they sit flush against
# each other like a real tab strip instead of as separate spaced-out chips.
SOURCE_TAB_ROW_STYLE = (
    '<style>.st-key-source_tab_row [data-testid="stHorizontalBlock"] { gap: 0 !important; }</style>'
)


def build_source_tab_style(container_key: str, color: str, corner: str, active: bool) -> str:
    """CSS for one playlist-source tab: gray background with the icon in its
    own brand color when inactive, full brand-color background with a white
    icon (+ name label) when active - the width itself comes from the column
    ratio, not from anything here. The icon + label sit in an
    absolutely-positioned row on top of an invisible full-size button
    underneath, so the visible shape is a single flat badge rather than an
    icon stacked above a separate button box. `corner` ("first"/"middle"/
    "last") rounds only the tab strip's outer ends."""
    radius = {
        "first": "10px 0 0 10px",
        "middle": "0",
        "last": "0 10px 10px 0",
    }[corner]
    bg = color if active else "rgba(128,128,128,0.08)"
    icon_color = "white" if active else color
    return (
        "<style>"
        # .st-key-<key> is applied directly to the stVerticalBlock produced by
        # st.container(key=...) - not some separate outer wrapper - so it's the
        # positioning context itself, and its own height must be forced with
        # !important since Streamlit's own rule otherwise wins.
        f".st-key-{container_key} {{"
        f"position: relative !important;"
        f"height: 40px !important;"
        f"min-height: 40px !important;"
        f"background-color: {bg} !important;"
        f"border-radius: {radius} !important;"
        f"overflow: hidden !important;"
        f"gap: 0 !important;"
        f"transition: background-color 0.2s ease;"
        f"}}"
        f".st-key-{container_key} .tab-content {{"
        f"position: absolute !important;"
        f"top: 0 !important; left: 0 !important; right: 0 !important;"
        f"height: 40px !important;"
        f"display: flex; align-items: center; justify-content: center; gap: 8px;"
        f"padding: 0 12px; pointer-events: none; white-space: nowrap; overflow: hidden;"
        f"color: {icon_color};"
        f"}}"
        f".st-key-{container_key} .tab-label {{ color: white; font-weight: 600; font-size: 0.85rem; }}"
        f'.st-key-{container_key} [data-testid="stButton"] {{'
        f"position: absolute !important; top: 0 !important; left: 0 !important; right: 0 !important;"
        f"height: 40px !important;"
        f"}}"
        f".st-key-{container_key} button {{"
        f"width: 100%; height: 100%;"
        f"background-color: transparent !important;"
        f"border: none !important;"
        f"box-shadow: none !important;"
        f"opacity: 0 !important;"
        f"}}"
        "</style>"
    )


STEPS = ["Match", "Download", "Convert"]

# (background, text color) per status, keyed to the step container's own CSS class
# (Streamlit gives every st.container(key=...) a ".st-key-<key>" class to target).
STEP_STATUS_COLORS = {
    "pending": ("rgba(128,128,128,0.15)", "rgba(128,128,128,0.8)"),
    "active": ("rgba(76,175,80,0.55)", "white"),
    "done": ("rgba(76,175,80,0.9)", "white"),
}


def build_step_container_style(container_key: str, status: str) -> str:
    bg, text_color = STEP_STATUS_COLORS[status]
    box_rule = (
        f".st-key-{container_key} {{"
        f"background-color: {bg} !important;"
        f"border: none !important;"
        f"border-radius: 10px !important;"
        f"min-height: 110px;"
        f"transition: background-color 0.4s ease;"
        f"}}"
    )
    vertical_block_rule = (
        f'.st-key-{container_key} [data-testid="stVerticalBlock"] {{'
        f"height: 100%;"
        f"display: flex;"
        f"flex-direction: column;"
        f"}}"
    )
    label_area_rule = (
        f'.st-key-{container_key} [data-testid="stElementContainer"]:first-of-type {{'
        f"flex: 1;"
        f"display: flex;"
        f"align-items: center;"
        f"justify-content: center;"
        f"}}"
    )
    text_rule = (
        f".st-key-{container_key} p {{"
        f"color: {text_color} !important;"
        f"font-weight: 600;"
        f"font-size: 1.05rem;"
        f"text-align: center;"
        f"margin: 0;"
        f"transition: color 0.4s ease;"
        f"}}"
    )
    return f"<style>{box_rule}{vertical_block_rule}{label_area_rule}{text_rule}</style>"


def build_step_label_html(name: str, status: str) -> str:
    check = " ✓" if status == "done" else ""
    return f"<p>{html.escape(name)}{check}</p>"


def _format_duration(duration_seconds) -> str:
    try:
        total_seconds = int(float(duration_seconds))
    except (TypeError, ValueError):
        return ""
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes}:{seconds:02d}"


def _format_artist_names(raw_artist_names) -> str:
    names = [name.strip() for name in re.split(r"[,;]", str(raw_artist_names)) if name.strip()]
    return ", ".join(names)


def _build_track_state_badge_html(row: dict) -> str:
    state = row.get("State", "")
    color = STATE_COLORS.get(state, (128, 128, 128))
    return (
        f'<span class="state-badge" style="background-color: rgba({color[0]},{color[1]},{color[2]},0.15); '
        f'color: rgb({color[0]},{color[1]},{color[2]});">{html.escape(state)}</span>'
    )


def _build_hardware_compat_badge_html(row: dict) -> str:
    findings = row.get(ROW_KEY_HARDWARE_COMPAT_FINDINGS)
    if not findings:
        return ""
    worst_fail = any(level == HARDWARE_COMPAT_FAIL for level, _ in findings)
    css_class = "compat-fail" if worst_fail else "compat-warn"
    icon = "⛔" if worst_fail else "⚠"
    tooltip = html.escape(" | ".join(f"{level}: {message}" for level, message in findings))
    count = len(findings)
    return f'<span class="compat-badge {css_class}" title="{tooltip}">{icon} {count}</span>'


def _build_track_bottom_html(row: dict) -> str:
    annotation_parts = []
    duration_str = _format_duration(row.get(COLUMN_TRACK_DURATION))
    if duration_str:
        annotation_parts.append(duration_str)
    tempo = row.get(COLUMN_TEMPO)
    if tempo:
        annotation_parts.append(f"{tempo} BPM")
    bit_rate = row.get(COLUMN_BIT_RATE)
    if bit_rate:
        annotation_parts.append(f"{bit_rate} kbps")
    annotations = html.escape(" · ".join(annotation_parts))

    genre_list = [g.strip() for g in str(row.get(COLUMN_GENRES, "")).split(",") if g.strip()]
    genre_tags = "".join(f'<span class="genre-tag">{html.escape(g)}</span>' for g in genre_list)

    return (
        '<div class="track-card-bottom">'
        f'<div class="track-annotations">{annotations}</div>'
        f'<div class="track-genres">{genre_tags}</div>'
        "</div>"
    )


def build_track_card_html(row: dict) -> str:
    if soundcloud_url := row.get(COLUMN_SOUNDCLOUD_URL):
        source_url = html.escape(soundcloud_url)
        yt_element = f'<a class="sc-link" href="{source_url}" target="_blank">▶ SoundCloud</a>'
    elif row.get(COLUMN_YOUTUBE_ID):
        yt_url = html.escape(get_youtube_url(row))
        yt_element = f'<a class="yt-link" href="{yt_url}" target="_blank">▶ YouTube</a>'
    else:
        yt_element = '<span class="yt-link-disabled">▶ Play</span>'

    track_name = html.escape(str(row.get(COLUMN_TRACK_NAME, "")))
    artist_name = html.escape(_format_artist_names(row.get(COLUMN_ARTIST_NAME, "")))

    return (
        '<div class="track-card">'
        '<div class="track-card-top">'
        f'<div><span class="track-title">{track_name}</span>'
        f'<span class="track-artist">{artist_name}</span></div>'
        f'<div class="track-actions">{_build_track_state_badge_html(row)}'
        f"{_build_hardware_compat_badge_html(row)}{yt_element}</div>"
        "</div>" + _build_track_bottom_html(row) + "</div>"
    )


YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
YOUTUBE_URL_ID_RE = re.compile(r"(?:v=|youtu\.be/|embed/|shorts/)([A-Za-z0-9_-]{11})")


def extract_youtube_id(text: str):
    """Pull an 11-char Youtube video ID out of a pasted URL, or accept a raw ID directly."""
    text = (text or "").strip()
    if not text:
        return None
    if YOUTUBE_ID_RE.match(text):
        return text
    match = YOUTUBE_URL_ID_RE.search(text)
    return match.group(1) if match else None

st.set_page_config(page_title="Track Tracker", page_icon="🎵", layout="wide")
st.title("Track Tracker")
st.caption("Turn a Spotify, Tidal or YouTube playlist into a folder of tagged MP3s.")


def build_tracks(csv_path: str):
    """Load the CSV and initialize every row with a State, ready for the table."""
    _, header_columns = read_csv(csv_path)

    if COLUMN_YOUTUBE_ID in header_columns:
        rows = get_data_list_from_csv_with_ids(csv_path)
        display_columns = list(header_columns)
    else:
        rows, display_columns = get_data_list_from_exportify_csv(csv_path)
        display_columns = list(display_columns) + [COLUMN_YOUTUBE_ID]
        for row in rows:
            row.setdefault(COLUMN_YOUTUBE_ID, "")

    if COLUMN_SOUNDCLOUD_URL not in display_columns:
        display_columns = display_columns + [COLUMN_SOUNDCLOUD_URL]
    for row in rows:
        row.setdefault(COLUMN_SOUNDCLOUD_URL, "")

    if COLUMN_BIT_RATE not in display_columns:
        display_columns = display_columns + [COLUMN_BIT_RATE]
    for row in rows:
        row.setdefault(COLUMN_BIT_RATE, "")

    for row in rows:
        row["State"] = (
            STATE_MATCHED if row.get(COLUMN_YOUTUBE_ID) or row.get(COLUMN_SOUNDCLOUD_URL) else STATE_PENDING
        )

    return rows, ["State"] + display_columns


def get_playlist_name(csv_filename: str) -> str:
    return os.path.splitext(csv_filename)[0]


def get_download_dir(dest_root: str, csv_filename: str) -> str:
    return os.path.join(dest_root, get_playlist_name(csv_filename))


def sync_states_from_disk(download_dir: str):
    """Pick up tracks that are already downloaded/converted on disk from a previous
    run, so the list reflects real progress as soon as the CSV or output folder is set."""
    if not os.path.isdir(download_dir):
        return
    for row in st.session_state.tracks:
        song_filename = get_song_filename(row)
        if os.path.exists(os.path.join(download_dir, song_filename + ".mp3")):
            row["State"] = STATE_CONVERTED
        elif os.path.exists(os.path.join(download_dir, song_filename + ".mp4")):
            row["State"] = STATE_DOWNLOADED


def activate_csv_source(csv_bytes: bytes, csv_name: str, source_id: str):
    """Load a CSV into session state. Shared by the file uploader and the Spotify
    picker below so the rest of the pipeline doesn't care which one supplied it."""
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp.write(csv_bytes)
        tmp_csv_path = tmp.name
    st.session_state.tracks, st.session_state.display_columns = build_tracks(tmp_csv_path)
    st.session_state.uploaded_file_id = source_id
    st.session_state.uploaded_file_name = csv_name
    st.session_state.csv_bytes = bytes(csv_bytes)


def handle_spotify_playlist_selected(playlist: dict):
    """Export the chosen Spotify playlist to a CSV and load it exactly like an upload."""
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp_csv_path = tmp.name
    export_spotify_playlist_to_csv(st.session_state.spotify_client, playlist["id"], tmp_csv_path)
    with open(tmp_csv_path, "rb") as f:
        csv_bytes = f.read()
    csv_name = sanitize_filename(playlist["name"]) + ".csv"
    activate_csv_source(csv_bytes, csv_name, f"spotify:{playlist['id']}")


def handle_tidal_playlist_selected(playlist: dict):
    """Export the chosen Tidal playlist to a CSV and load it exactly like an upload."""
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp_csv_path = tmp.name
    export_tidal_playlist_to_csv(st.session_state.tidal_session, playlist["id"], tmp_csv_path)
    with open(tmp_csv_path, "rb") as f:
        csv_bytes = f.read()
    csv_name = sanitize_filename(playlist["name"]) + ".csv"
    activate_csv_source(csv_bytes, csv_name, f"tidal:{playlist['id']}")


def handle_youtube_playlist_url(playlist_id: str) -> int:
    """Export the pasted YouTube playlist to a CSV and load it exactly like an
    upload. Returns how many unavailable entries were skipped, so the sidebar
    can mention them."""
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp_csv_path = tmp.name
    playlist_title, skipped = export_youtube_playlist_to_csv(playlist_id, tmp_csv_path)
    with open(tmp_csv_path, "rb") as f:
        csv_bytes = f.read()
    csv_name = sanitize_filename(playlist_title) + ".csv"
    activate_csv_source(csv_bytes, csv_name, f"youtube:{playlist_id}")
    return skipped


def handle_oauth_callback():
    """Spotify uses a redirect-based OAuth flow that lands back on this same
    app URL with a `code` param - `state` (set when building the login URL)
    marks it as a Spotify callback. Tidal uses a device-code flow instead (see
    render_tidal_sidebar), so it has no callback to handle here. Runs once,
    before any sidebar panel renders, regardless of which one is currently
    selected."""
    code = st.query_params.get("code")
    state = st.query_params.get("state")
    if not code:
        return

    if state == "spotify" and "spotify_client" not in st.session_state:
        try:
            st.session_state.spotify_client = complete_spotify_login(code)
        except SPOTIFY_ERRORS + (RuntimeError,) as exc:
            st.sidebar.error(f"Spotify login failed: {exc}")
        st.query_params.clear()
        st.rerun()


def render_spotify_sidebar():
    """Left pane: log into Spotify, then pick a playlist from a list, mirroring
    Exportify's own login-then-pick flow instead of asking for a pasted URL."""
    st.sidebar.subheader("Spotify")

    if not SPOTIFY_CLIENT_ID:
        st.sidebar.warning(
            "Spotify login is disabled: set SPOTIFY_CLIENT_ID in a .env file "
            "(see .env.example). You can still upload an Exportify CSV below."
        )
        return

    if "spotify_client" not in st.session_state:
        cached_client = get_cached_spotify_client(SPOTIFY_CLIENT_ID)
        if cached_client:
            st.session_state.spotify_client = cached_client

    if "spotify_client" not in st.session_state:
        st.sidebar.caption(
            "Rather than uploading an Exportify CSV, you can log into your Spotify "
            "account and your playlists will be displayed here. Note that due to "
            "Spotify API changes in Nov 2024, Tempo and Genres are no longer "
            "available for new apps such as this one."
        )
        login_url = build_spotify_login_url(SPOTIFY_CLIENT_ID)
        st.sidebar.markdown(
            SPOTIFY_SIDEBAR_STYLE + f'<a class="spotify-login-link" href="{html.escape(login_url)}" '
            'target="_self">Login to Spotify</a>',
            unsafe_allow_html=True,
        )
        return

    if st.sidebar.button("Log out", key="spotify_logout"):
        spotify_logout()
        for key in ("spotify_client", "spotify_playlists"):
            st.session_state.pop(key, None)
        st.rerun()

    if "spotify_playlists" not in st.session_state:
        try:
            st.session_state.spotify_playlists = list_spotify_playlists(st.session_state.spotify_client)
        except SPOTIFY_ERRORS as exc:
            # Don't cache a failure - leaving the key unset means this retries on
            # the next rerun instead of getting stuck on a stale empty list.
            st.sidebar.error(f"Couldn't load playlists: {exc}")

    st.sidebar.markdown(SPOTIFY_SIDEBAR_STYLE, unsafe_allow_html=True)
    for playlist in st.session_state.get("spotify_playlists", []):
        image_col, name_col, select_col = st.sidebar.columns([1, 4, 1])
        with image_col:
            if playlist["image_url"]:
                st.image(playlist["image_url"], width=36)
            else:
                st.markdown('<div class="playlist-row-placeholder"></div>', unsafe_allow_html=True)
        with name_col:
            st.markdown(
                f'<div class="playlist-row-name">{html.escape(playlist["name"])}</div>',
                unsafe_allow_html=True,
            )
        with select_col:
            if st.button("➜", key=f"select_playlist_{playlist['id']}"):
                try:
                    handle_spotify_playlist_selected(playlist)
                except SPOTIFY_ERRORS as exc:
                    st.sidebar.error(f"Couldn't load '{playlist['name']}': {exc}")
                else:
                    st.rerun()


def render_tidal_sidebar():
    """Left pane: log into Tidal via a device-code flow (tidalapi ships its own
    working client credentials, unlike Spotify - no developer registration
    needed), then pick a playlist from a list."""
    st.sidebar.subheader("Tidal")

    if "tidal_session" not in st.session_state:
        cached_session = get_cached_tidal_session()
        if cached_session:
            st.session_state.tidal_session = cached_session

    if "tidal_session" not in st.session_state:
        st.sidebar.caption(
            "Rather than uploading a CSV, you can log into Tidal and your "
            "playlists will be displayed here. Requires an active Tidal "
            "subscription or trial - unlike Spotify, Tidal has no free tier."
        )
        if "tidal_link_login" not in st.session_state:
            if st.sidebar.button("Login to Tidal", key="tidal_login_start"):
                try:
                    st.session_state.tidal_link_login = start_tidal_login()
                except TIDAL_ERRORS as exc:
                    st.sidebar.error(f"Couldn't start Tidal login: {exc}")
                else:
                    st.rerun()
        else:
            link_login = st.session_state.tidal_link_login
            verification_url = f"https://{link_login.verification_uri_complete}"
            st.sidebar.markdown(
                f"Go to [{verification_url}]({verification_url}) and confirm the code "
                f"**{link_login.user_code}**, then click below."
            )
            if st.sidebar.button("I've authorized - Continue", key="tidal_login_continue"):
                try:
                    session = try_complete_tidal_login(link_login)
                except TIDAL_ERRORS as exc:
                    st.sidebar.error(f"Tidal login failed: {exc}")
                    del st.session_state["tidal_link_login"]
                else:
                    if session is None:
                        st.sidebar.warning(
                            "Not authorized yet - finish the steps above, then click again."
                        )
                    else:
                        st.session_state.tidal_session = session
                        del st.session_state["tidal_link_login"]
                        st.rerun()
        return

    if st.sidebar.button("Log out", key="tidal_logout"):
        tidal_logout()
        for key in ("tidal_session", "tidal_playlists"):
            st.session_state.pop(key, None)
        st.rerun()

    if "tidal_playlists" not in st.session_state:
        try:
            st.session_state.tidal_playlists = list_tidal_playlists(st.session_state.tidal_session)
        except TIDAL_ERRORS as exc:
            st.sidebar.error(f"Couldn't load playlists: {exc}")

    st.sidebar.markdown(SPOTIFY_SIDEBAR_STYLE, unsafe_allow_html=True)
    for playlist in st.session_state.get("tidal_playlists", []):
        image_col, name_col, select_col = st.sidebar.columns([1, 4, 1])
        with image_col:
            if playlist["image_url"]:
                st.image(playlist["image_url"], width=36)
            else:
                st.markdown('<div class="playlist-row-placeholder"></div>', unsafe_allow_html=True)
        with name_col:
            st.markdown(
                f'<div class="playlist-row-name">{html.escape(playlist["name"])}</div>',
                unsafe_allow_html=True,
            )
        with select_col:
            if st.button("➜", key=f"select_tidal_playlist_{playlist['id']}"):
                try:
                    handle_tidal_playlist_selected(playlist)
                except TIDAL_ERRORS as exc:
                    st.sidebar.error(f"Couldn't load '{playlist['name']}': {exc}")
                else:
                    st.rerun()


def render_youtube_sidebar():
    """Left pane: paste a YouTube/YouTube Music playlist URL. No login flow at
    all (unauthenticated ytmusicapi handles public/unlisted playlists), and no
    picker list - one URL is one playlist, so it activates immediately."""
    st.sidebar.subheader("YouTube")

    # One-shot note from the previous run's activation, surfaced after the
    # rerun so it isn't lost with the rest of that script run's output.
    skipped_note = st.session_state.pop("youtube_skipped_note", None)
    if skipped_note:
        st.sidebar.caption(skipped_note)

    st.sidebar.caption(
        "Paste a link to a public or unlisted YouTube / YouTube Music "
        "playlist - no login needed. Its videos are used directly, so tracks "
        "arrive pre-matched and the Matching step is skipped."
    )
    url_col, go_col = st.sidebar.columns([3, 1])
    with url_col:
        playlist_url = st.text_input(
            "YouTube playlist URL",
            key="youtube_playlist_url",
            label_visibility="collapsed",
            placeholder="youtube.com/playlist?list=...",
        )
    with go_col:
        go_clicked = st.button("➜", key="youtube_playlist_go", width="stretch")
    if not go_clicked:
        return

    playlist_id = extract_youtube_playlist_id(playlist_url)
    if not playlist_id:
        st.sidebar.error("Couldn't find a playlist ID in that link.")
        return
    try:
        skipped = handle_youtube_playlist_url(playlist_id)
    except YOUTUBE_ERRORS as exc:
        st.sidebar.error(str(exc))
        return
    if skipped:
        st.session_state["youtube_skipped_note"] = f"{skipped} unavailable track(s) skipped."
    st.rerun()


def render_source_tab_bar():
    """Tabs for picking the playlist source, flush against each other with no
    gaps: each tab is a flat badge in its own brand color, a small square when
    inactive (logo only) and a wider rectangle when active (logo + name) - the
    width itself comes from the column ratio. A real st.button (made fully
    invisible but still clickable) is layered on top of the visible content
    via absolute positioning, so clicking is a normal Streamlit rerun over the
    existing connection, not a browser navigation/full page reload."""
    st.session_state.setdefault("playlist_source", PLAYLIST_SOURCES[0][0])
    active_source = st.session_state.playlist_source

    with st.sidebar.container(key="source_tab_row"):
        st.markdown(SOURCE_TAB_ROW_STYLE, unsafe_allow_html=True)
        ratios = [3 if name == active_source else 1 for name, _, _, _ in PLAYLIST_SOURCES]
        tab_cols = st.sidebar.columns(ratios, gap=None)
        for i, (col, (name, glyph_svg, badge_svg, color)) in enumerate(zip(tab_cols, PLAYLIST_SOURCES)):
            is_active = name == active_source
            tab_key = f"tab_{name.replace(' ', '_').lower()}"
            corner = "first" if i == 0 else "last" if i == len(PLAYLIST_SOURCES) - 1 else "middle"
            with col, st.container(key=tab_key, border=False):
                st.markdown(build_source_tab_style(tab_key, color, corner, is_active), unsafe_allow_html=True)
                logo_svg = glyph_svg if is_active else badge_svg
                label_html = f'<span class="tab-label">{html.escape(name)}</span>' if is_active else ""
                st.markdown(f'<div class="tab-content">{logo_svg}{label_html}</div>', unsafe_allow_html=True)
                if st.button("select", key=f"{tab_key}_btn", width="stretch"):
                    st.session_state.playlist_source = name
                    st.rerun()


def render_playlist_sidebar():
    """Left pane entry point: let the user pick which service supplies playlist
    data, then render that service's login/playlist-picker flow."""
    handle_oauth_callback()
    render_source_tab_bar()
    source = st.session_state.playlist_source
    if source == "Spotify":
        render_spotify_sidebar()
    elif source == "Tidal":
        render_tidal_sidebar()
    else:
        render_youtube_sidebar()


render_playlist_sidebar()

uploader_col, destination_col = st.columns(2)
with uploader_col:
    uploaded_file = st.file_uploader(
        "Alternatively upload an Exportify CSV file",
        type="csv",
        help="An Exportify export, or a CSV that already has a 'Youtube ID' column.",
    )
with destination_col:
    destination_root = st.text_input(
        "Save music to",
        value=str(Path.home() / "Music" / "MusicDownloads"),
        help="Each playlist gets its own folder (named after the CSV) inside here.",
    )

if uploaded_file is not None and st.session_state.get("uploaded_file_id") != uploaded_file.file_id:
    activate_csv_source(bytes(uploaded_file.getbuffer()), uploaded_file.name, uploaded_file.file_id)

if "tracks" in st.session_state and destination_root:
    sync_states_from_disk(get_download_dir(destination_root, st.session_state.uploaded_file_name))

# Each step is only runnable while there are tracks in a state it acts on. Besides its
# natural input state, a step also accepts rows stranded in its own transient states:
# any Streamlit interaction kills the running script mid-stage, and a row frozen in
# "Downloading"/"Retrying"/"Converting" would otherwise be unreachable by every stage,
# deadlocking the UI with all Run buttons disabled.
DOWNLOAD_ELIGIBLE_STATES = {
    STATE_MATCHED,
    STATE_DOWNLOADING,
    STATE_RETRYING,
    STATE_FAILED_BEFORE_RETRY,
}
CONVERT_ELIGIBLE_STATES = {STATE_DOWNLOADED, STATE_CONVERTING}
STEP_PRECONDITION_STATES = [{STATE_PENDING}, DOWNLOAD_ELIGIBLE_STATES, CONVERT_ELIGIBLE_STATES]


def count_tracks_in_states(states) -> int:
    if "tracks" not in st.session_state:
        return 0
    return sum(1 for row in st.session_state.tracks if row["State"] in states)


def render_unmatched_tracks_panel():
    """After a Matching run, let the user manually supply a Youtube link for any track
    that couldn't be auto-matched, right under the Matching card."""
    if "tracks" not in st.session_state:
        return
    unmatched = [
        (idx, row)
        for idx, row in enumerate(st.session_state.tracks)
        if row["State"] == STATE_NO_MATCH
    ]
    if not unmatched:
        return

    st.caption(f"{len(unmatched)} track(s) need a manual link:")
    for idx, row in unmatched:
        label = f"{row.get(COLUMN_ARTIST_NAME, '')} - {row.get(COLUMN_TRACK_NAME, '')}"
        input_col, confirm_col = st.columns([3, 1])
        with input_col:
            manual_value = st.text_input(
                label,
                key=f"yt_manual_{idx}",
                label_visibility="collapsed",
                placeholder=label,
            )
        with confirm_col:
            confirm_clicked = st.button("✓", key=f"yt_manual_confirm_{idx}", width="stretch")
        if confirm_clicked:
            video_id = extract_youtube_id(manual_value)
            if video_id:
                row[COLUMN_YOUTUBE_ID] = video_id
                row["State"] = STATE_MATCHED
                st.rerun()
            else:
                st.error(f"Couldn't find a Youtube video ID in that link for '{label}'.")


options_col, steps_col = st.columns([1, 3])
with options_col:
    target_device = st.selectbox(
        "Target device",
        ["Custom"] + list(DEVICE_PROFILES.keys()),
        index=0,
        help="Caps the MP3 bitrate at what the device supports, and flags each "
        "downloaded track with hardware-compatibility warnings for that device.",
    )
    if target_device == "Custom":
        device_profile = None
        bitrate_checkbox_col, bitrate_select_col = st.columns([2, 3], vertical_alignment="center")
        with bitrate_checkbox_col:
            use_max_bitrate = st.checkbox("Max available bitrate", value=True)
        with bitrate_select_col:
            bitrate = st.selectbox(
                "MP3 bitrate",
                ["128k", "192k", "256k", "320k"],
                index=0,
                label_visibility="collapsed",
                disabled=use_max_bitrate,
            )
    else:
        device_profile = DEVICE_PROFILES[target_device]
        use_max_bitrate = True
        bitrate = f"{device_profile.max_mp3_kbps}k"
        supported_formats = ", ".join(fmt.upper() for fmt in device_profile.formats)
        sample_rate_note = (
            f"up to {device_profile.max_sample_rate_hz // 1000}kHz"
            if device_profile.max_sample_rate_hz
            else "no device ceiling"
        )
        st.caption(
            f"Supports {supported_formats} · MP3 capped at {device_profile.max_mp3_kbps}kbps · "
            f"sample rate {sample_rate_note} (output is still MP3-only — tracks that would "
            f"need another format to fit this device show up as warnings after download)"
        )
    artist_col, delete_col = st.columns(2)
    with artist_col:
        artist_in_title = st.checkbox(
            "Include artist in track title",
            value=False,
            help="Store metadata title as 'ARTIST - TRACK TITLE' instead of just 'TRACK TITLE'.",
        )
    with delete_col:
        delete_originals = st.checkbox(
            "Delete original files after MP3 conversion", value=True
        )

with steps_col:
    step_cols = st.columns(3)
    step_containers = []  # (container_key, label_placeholder)
    step_clicked = []
    for col, name, precondition_states in zip(step_cols, STEPS, STEP_PRECONDITION_STATES):
        with col:
            container_key = f"step_card_{name.lower()}"
            with st.container(key=container_key, border=False):
                label_placeholder = st.empty()
                eligible = count_tracks_in_states(precondition_states) > 0
                step_clicked.append(
                    st.button("Run", key=f"run_{name.lower()}", disabled=not eligible, width="stretch")
                )
            step_containers.append((container_key, label_placeholder))
            if name == "Match":
                render_unmatched_tracks_panel()
    run_matching_clicked, run_downloading_clicked, run_converting_clicked = step_clicked

    start = st.button(
        "Start", type="primary", disabled="uploaded_file_name" not in st.session_state, width="stretch"
    )


def render_steps(statuses):
    for (container_key, label_placeholder), name, status in zip(step_containers, STEPS, statuses):
        label_placeholder.markdown(
            build_step_container_style(container_key, status) + build_step_label_html(name, status),
            unsafe_allow_html=True,
        )


render_steps(["pending"] * len(STEPS))

title_col, genre_summary_col = st.columns([1, 3])
with title_col:
    st.subheader("Tracks")
genre_summary_placeholder = genre_summary_col.empty()
tracks_placeholder = st.empty()


def render_genre_summary():
    if "tracks" not in st.session_state:
        return
    counts = Counter()
    for row in st.session_state.tracks:
        for genre in str(row.get(COLUMN_GENRES, "")).split(","):
            genre = genre.strip()
            if genre:
                counts[genre] += 1
    if not counts:
        return
    tags = "".join(
        f'<span class="genre-tag">{html.escape(genre)}</span>'
        for genre, _ in counts.most_common()
    )
    genre_summary_placeholder.markdown(
        TRACK_CARD_STYLE + f'<div class="genre-summary">{tags}</div>',
        unsafe_allow_html=True,
    )


def render_tracks():
    render_genre_summary()
    if "tracks" not in st.session_state:
        tracks_placeholder.info("Upload a CSV to see your tracks here.")
        return
    cards = "".join(build_track_card_html(row) for row in st.session_state.tracks)
    tracks_placeholder.markdown(TRACK_CARD_STYLE + cards, unsafe_allow_html=True)


render_tracks()


def run_matching_stage():
    pending_rows = [row for row in st.session_state.tracks if row["State"] == STATE_PENDING]
    total = len(pending_rows)
    if total == 0:
        return
    for row in pending_rows:
        search_string = get_song_search_string(row)

        soundcloud_url = None
        try:
            soundcloud_results = search_soundcloud_tracks(search_string)
            soundcloud_url = find_best_matching_soundcloud_track(
                db_entry=row, search_results=soundcloud_results
            )
        except NoMatchingSoundcloudTrackFoundError:
            pass
        except Exception as exc:
            # SoundCloud is an unofficial API (scraped client_id, reverse-engineered
            # endpoints) - any failure here just means falling back to YouTube below,
            # not failing the match.
            print(f"SoundCloud search failed for '{search_string}': {exc}")

        if soundcloud_url:
            row[COLUMN_SOUNDCLOUD_URL] = soundcloud_url
            row["State"] = STATE_MATCHED
            render_tracks()
            continue

        try:
            results = get_youtube_music_search_results(search_string)
            video_id = find_best_matching_youtube_music_video(db_entry=row, search_results=results)
        except NoMatchingYoutubeMusicVideoFoundError:
            row["State"] = STATE_NO_MATCH
        else:
            row[COLUMN_YOUTUBE_ID] = video_id
            row["State"] = STATE_MATCHED
        render_tracks()


def _download_track_audio(row: dict, download_dir: str, song_filename: str) -> str:
    """Download a track's audio, preferring SoundCloud when matched but falling
    back to YouTube if the SoundCloud download itself fails. Some tracks (e.g.
    ad-monetized/label-affiliated ones) list a progressive stream in their
    metadata that 404s in practice - SoundCloud only actually serves those via
    encrypted HLS, which we don't attempt to decrypt - so this is a real,
    expected fallback path, not just a rare edge case."""
    soundcloud_url = row.get(COLUMN_SOUNDCLOUD_URL)
    if soundcloud_url:
        try:
            return get_audio_from_soundcloud(
                track_url=soundcloud_url, output_dir=download_dir, filename=song_filename
            )
        except Exception as exc:
            print(f"SoundCloud download failed for '{song_filename}', falling back to YouTube: {exc}")
            row[COLUMN_SOUNDCLOUD_URL] = ""

    if not row.get(COLUMN_YOUTUBE_ID):
        results = get_youtube_music_search_results(get_song_search_string(row))
        row[COLUMN_YOUTUBE_ID] = find_best_matching_youtube_music_video(db_entry=row, search_results=results)

    return get_audio_from_youtube(
        youtube_url=get_youtube_url(row), output_dir=download_dir, filename=song_filename
    )


def _get_target_bitrate_kbps(row: dict) -> str:
    """What ffmpeg should target when (re-)encoding this row's mp3: the source's
    own native bitrate (capped at mp3's 320kbps ceiling) when "max available
    bitrate" is checked, or the user's explicitly selected bitrate otherwise."""
    if use_max_bitrate:
        native_kbps = row.get(COLUMN_BIT_RATE)
        if native_kbps:
            return f"{min(int(native_kbps), 320)}k"
    return bitrate


def _maybe_downsample_mp3(filepath: str, row: dict) -> None:
    """Re-encode a SoundCloud download down to the user's explicitly selected
    bitrate, if it's lower than what SoundCloud actually served. YouTube tracks
    get this from the conversion stage's own bitrate choice; SoundCloud downloads
    already land as mp3 with no separate conversion step, so this is the only
    place that request would otherwise get ignored."""
    if use_max_bitrate:
        return
    native_kbps = row.get(COLUMN_BIT_RATE)
    target_kbps = int(bitrate.rstrip("k"))
    if not native_kbps or int(native_kbps) <= target_kbps:
        return
    tmp_path = os.path.splitext(filepath)[0] + "_downsampled.mp3"
    if convert_to_mp3(filepath, tmp_path, bitrate):
        os.replace(tmp_path, filepath)
        row[COLUMN_BIT_RATE] = get_file_bit_rate_kbps(filepath)


def _run_hardware_compat_check(row: dict, filepath: str) -> None:
    """Check the final output file against the selected target device (or the
    generic device-agnostic warnings, if "Custom" is selected) and stash the
    findings on the row for the track card to display."""
    try:
        row[ROW_KEY_HARDWARE_COMPAT_FINDINGS] = check_hardware_compat(filepath, device_profile=device_profile)
    except Exception as exc:
        print(f"Hardware-compat check failed for '{filepath}': {exc}")


def run_download_stage(download_dir):
    pending_rows = [
        row for row in st.session_state.tracks if row["State"] in DOWNLOAD_ELIGIBLE_STATES
    ]
    total = len(pending_rows)
    if total == 0:
        return

    for retry_round in range(MAX_BOT_DETECTION_RETRIES + 1):
        if not pending_rows:
            break

        if retry_round > 0:
            delay = RETRY_BACKOFF_BASE_SECONDS * (2 ** (retry_round - 1)) + random.uniform(0, 1)
            time.sleep(delay)

        still_pending = []
        for row in pending_rows:
            row["State"] = STATE_RETRYING if retry_round > 0 else STATE_DOWNLOADING
            render_tracks()

            song_filename = get_song_filename(row)
            existing_ext = next(
                (
                    ext
                    for ext in SUPPORTED_FORMATS
                    if os.path.exists(os.path.join(download_dir, song_filename + ext))
                ),
                None,
            )
            if existing_ext:
                # A SoundCloud download already lands as mp3 (no conversion needed);
                # a YouTube one lands as mp4 and still needs the conversion stage.
                row["State"] = STATE_CONVERTED if existing_ext == FILE_EXTENSION_MP3 else STATE_DOWNLOADED
                existing_filepath = os.path.join(download_dir, song_filename + existing_ext)
                if not row.get(COLUMN_BIT_RATE):
                    row[COLUMN_BIT_RATE] = get_file_bit_rate_kbps(existing_filepath)
                if existing_ext == FILE_EXTENSION_MP3 and ROW_KEY_HARDWARE_COMPAT_FINDINGS not in row:
                    _run_hardware_compat_check(row, existing_filepath)
            else:
                try:
                    output_filepath = _download_track_audio(row, download_dir, song_filename)
                    row[COLUMN_BIT_RATE] = get_file_bit_rate_kbps(output_filepath)
                    if not row.get(COLUMN_TEMPO):
                        try:
                            row[COLUMN_TEMPO] = str(round(estimate_tempo(output_filepath)))
                        except Exception:
                            # Best-effort: leave Tempo blank rather than failing an
                            # otherwise-successful download over a bad BPM estimate.
                            pass
                    file_extension = os.path.splitext(output_filepath)[1]
                    metadata_tags = prepare_metadata_tags(
                        music_df_row=row,
                        file_extension=file_extension,
                        artist_in_title=artist_in_title,
                    )
                    set_file_metadata_tags(filepath=output_filepath, metadata_tags=metadata_tags)
                    if file_extension == FILE_EXTENSION_MP3:
                        _maybe_downsample_mp3(output_filepath, row)
                        _run_hardware_compat_check(row, output_filepath)
                except BotDetection:
                    row["State"] = STATE_FAILED_BEFORE_RETRY
                    still_pending.append(row)
                except Exception as exc:
                    source = "SoundCloud" if row.get(COLUMN_SOUNDCLOUD_URL) else "YouTube"
                    print(f"Error downloading '{song_filename}' from {source}: {exc}")
                    row["State"] = STATE_FAILED
                else:
                    row["State"] = STATE_CONVERTED if file_extension == FILE_EXTENSION_MP3 else STATE_DOWNLOADED

            render_tracks()

        pending_rows = still_pending

    for row in pending_rows:
        row["State"] = STATE_FAILED
    if pending_rows:
        render_tracks()


def run_conversion_stage(download_dir):
    filename_to_row = {
        get_song_filename(row): row
        for row in st.session_state.tracks
        if row["State"] in CONVERT_ELIGIBLE_STATES
    }
    audio_files = list(scan_directory_for_audio_files(download_dir, {FILE_EXTENSION_MP4}))
    if not audio_files:
        return

    for filepath in audio_files:
        song_filename = os.path.splitext(os.path.basename(filepath))[0]
        row = filename_to_row.get(song_filename)

        mp3_path = os.path.splitext(filepath)[0] + ".mp3"
        if os.path.exists(mp3_path):
            if row is not None:
                row["State"] = STATE_CONVERTED
                if not row.get(COLUMN_BIT_RATE):
                    row[COLUMN_BIT_RATE] = get_file_bit_rate_kbps(mp3_path)
                if ROW_KEY_HARDWARE_COMPAT_FINDINGS not in row:
                    _run_hardware_compat_check(row, mp3_path)
        else:
            if row is not None:
                row["State"] = STATE_CONVERTING
                render_tracks()
            target_bitrate = _get_target_bitrate_kbps(row) if row is not None else bitrate
            success = convert_to_mp3(filepath, mp3_path, target_bitrate)
            if row is not None:
                row["State"] = STATE_CONVERTED if success else STATE_FAILED_CONVERTING
                if success:
                    row[COLUMN_BIT_RATE] = get_file_bit_rate_kbps(mp3_path)
                    _run_hardware_compat_check(row, mp3_path)
            if success and delete_originals:
                os.remove(filepath)

        render_tracks()


if start or run_matching_clicked or run_downloading_clicked or run_converting_clicked:
    playlist_name = get_playlist_name(st.session_state.uploaded_file_name)
    download_dir = get_download_dir(destination_root, st.session_state.uploaded_file_name)
    os.makedirs(download_dir, exist_ok=True)
    st.info(f"Working in: `{download_dir}`")

    with open(os.path.join(download_dir, st.session_state.uploaded_file_name), "wb") as f:
        f.write(st.session_state.csv_bytes)

    data_columns = [c for c in st.session_state.display_columns if c != "State"]

    statuses = ["pending", "pending", "pending"]
    render_steps(statuses)

    if start or run_matching_clicked:
        statuses[0] = "active"
        render_steps(statuses)
        run_matching_stage()
        statuses[0] = "done"
        render_steps(statuses)

        matched_rows = [row for row in st.session_state.tracks if row["State"] != STATE_PENDING]
        write_csv(
            file_path=os.path.join(download_dir, f"{playlist_name}_with_ids.csv"),
            data=[
                {k: row[k] for k in data_columns}
                for row in matched_rows
                if row.get(COLUMN_YOUTUBE_ID) or row.get(COLUMN_SOUNDCLOUD_URL)
            ],
            fieldnames=data_columns,
        )
        unmatched_rows = [row for row in st.session_state.tracks if row["State"] == STATE_NO_MATCH]
        if unmatched_rows:
            unmatched_columns = [c for c in data_columns if c not in (COLUMN_YOUTUBE_ID, COLUMN_SOUNDCLOUD_URL)]
            write_csv(
                file_path=os.path.join(download_dir, f"{playlist_name}_without_ids.csv"),
                data=[{k: row[k] for k in unmatched_columns} for row in unmatched_rows],
                fieldnames=unmatched_columns,
            )
            st.warning(f"{len(unmatched_rows)} song(s) had no matching track on SoundCloud or YouTube.")

    if start or run_downloading_clicked:
        statuses[1] = "active"
        render_steps(statuses)
        run_download_stage(download_dir)
        statuses[1] = "done"
        render_steps(statuses)

    if start or run_converting_clicked:
        statuses[2] = "active"
        render_steps(statuses)
        run_conversion_stage(download_dir)
        statuses[2] = "done"
        render_steps(statuses)

    states = [row["State"] for row in st.session_state.tracks]
    done = states.count(STATE_DOWNLOADED) + states.count(STATE_CONVERTED)
    failed = states.count(STATE_FAILED) + states.count(STATE_FAILED_CONVERTING) + states.count(STATE_NO_MATCH)
    st.success(f"Done! {done} track(s) ready, {failed} failed, in `{download_dir}`.")

    # Track states just changed (e.g. matching produced new Matched rows) - rerun so the
    # step buttons re-evaluate their disabled state against the fresh data.
    st.rerun()
