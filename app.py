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

import spotipy
import streamlit as st
from pytubefix.exceptions import BotDetection

from convert_tracks_to_mp3 import convert_to_mp3
from src.csv_handling import read_csv, write_csv
from src.data_handling import (
    COLUMN_ARTIST_NAME,
    COLUMN_GENRES,
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
from src.file_handling import scan_directory_for_audio_files
from src.file_metadata import (
    FILE_EXTENSION_MP4,
    SUPPORTED_FORMATS,
    prepare_metadata_tags,
    set_file_metadata_tags,
)
from src.spotify_export import (
    SPOTIFY_CLIENT_ID,
    build_login_url,
    complete_login,
    export_playlist_to_csv,
    get_cached_spotify_client,
    list_user_playlists,
    logout,
)
from src.youtube_download import get_audio_from_youtube
from src.youtube_id_search import (
    NoMatchingYoutubeVideoFoundError,
    find_best_matching_youtube_id,
    get_youtube_search_results,
)

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
    ".yt-link, .yt-link-disabled { display: inline-block; font-size: 0.78rem; font-weight: 600; padding: 6px 14px; "
    "border-radius: 6px; text-decoration: none; white-space: nowrap; border: none; }"
    ".yt-link { background-color: #FF0000; color: white; box-shadow: 0 1px 2px rgba(0,0,0,0.25); cursor: pointer; }"
    ".yt-link:hover { background-color: #cc0000; }"
    ".yt-link-disabled { background-color: rgba(128,128,128,0.18); color: rgba(128,128,128,0.6); cursor: not-allowed; }"
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


def _build_track_bottom_html(row: dict) -> str:
    annotation_parts = []
    duration_str = _format_duration(row.get(COLUMN_TRACK_DURATION))
    if duration_str:
        annotation_parts.append(duration_str)
    tempo = row.get(COLUMN_TEMPO)
    if tempo:
        annotation_parts.append(f"{tempo} BPM")
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
    youtube_id = row.get(COLUMN_YOUTUBE_ID)
    if youtube_id:
        yt_url = html.escape(get_youtube_url(row))
        yt_element = f'<a class="yt-link" href="{yt_url}" target="_blank">▶ YouTube</a>'
    else:
        yt_element = '<span class="yt-link-disabled">▶ YouTube</span>'

    track_name = html.escape(str(row.get(COLUMN_TRACK_NAME, "")))
    artist_name = html.escape(_format_artist_names(row.get(COLUMN_ARTIST_NAME, "")))

    return (
        '<div class="track-card">'
        '<div class="track-card-top">'
        f'<div><span class="track-title">{track_name}</span>'
        f'<span class="track-artist">{artist_name}</span></div>'
        f'<div class="track-actions">{_build_track_state_badge_html(row)}{yt_element}</div>'
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

st.set_page_config(page_title="Music Downloader", page_icon="🎵", layout="wide")
st.title("Music Downloader")
st.caption("Turn a Spotify playlist (or an Exportify CSV export) into a folder of tagged MP3s.")


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

    for row in rows:
        row["State"] = STATE_MATCHED if row.get(COLUMN_YOUTUBE_ID) else STATE_PENDING

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


def handle_playlist_selected(playlist: dict):
    """Export the chosen Spotify playlist to a CSV and load it exactly like an upload."""
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp_csv_path = tmp.name
    export_playlist_to_csv(st.session_state.spotify_client, playlist["id"], tmp_csv_path)
    with open(tmp_csv_path, "rb") as f:
        csv_bytes = f.read()
    csv_name = sanitize_filename(playlist["name"]) + ".csv"
    activate_csv_source(csv_bytes, csv_name, f"spotify:{playlist['id']}")


def render_spotify_sidebar():
    """Left pane: log into Spotify, then pick a playlist from a list, mirroring
    Exportify's own login-then-pick flow instead of asking for a pasted URL."""
    st.sidebar.subheader("Spotify")

    code = st.query_params.get("code")
    if code and "spotify_client" not in st.session_state:
        try:
            st.session_state.spotify_client = complete_login(code)
        except (spotipy.SpotifyOauthError, RuntimeError) as exc:
            st.sidebar.error(f"Spotify login failed: {exc}")
            st.query_params.clear()
        else:
            st.query_params.clear()
            st.rerun()

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
        login_url = build_login_url(SPOTIFY_CLIENT_ID)
        st.sidebar.markdown(
            SPOTIFY_SIDEBAR_STYLE + f'<a class="spotify-login-link" href="{html.escape(login_url)}" '
            'target="_self">Login to Spotify</a>',
            unsafe_allow_html=True,
        )
        return

    if st.sidebar.button("Log out", key="spotify_logout"):
        logout()
        for key in ("spotify_client", "spotify_playlists"):
            st.session_state.pop(key, None)
        st.rerun()

    if "spotify_playlists" not in st.session_state:
        st.session_state.spotify_playlists = list_user_playlists(st.session_state.spotify_client)

    st.sidebar.markdown(SPOTIFY_SIDEBAR_STYLE, unsafe_allow_html=True)
    for playlist in st.session_state.spotify_playlists:
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
                    handle_playlist_selected(playlist)
                except spotipy.SpotifyException as exc:
                    st.sidebar.error(f"Couldn't load '{playlist['name']}': {exc}")
                else:
                    st.rerun()


render_spotify_sidebar()

uploader_col, destination_col = st.columns(2)
with uploader_col:
    uploaded_file = st.file_uploader(
        "CSV file",
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

# Each step is only runnable while there are tracks in the state it acts on.
STEP_PRECONDITION_STATES = [STATE_PENDING, STATE_MATCHED, STATE_DOWNLOADED]


def count_tracks_in_state(state) -> int:
    if "tracks" not in st.session_state:
        return 0
    return sum(1 for row in st.session_state.tracks if row["State"] == state)


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
    bitrate_label_col, bitrate_select_col = st.columns([1, 4], vertical_alignment="center")
    with bitrate_label_col:
        st.markdown(
            '<p style="font-size: 0.875rem; font-weight: 400; margin: -16px 0 0 0; white-space: nowrap;">'
            "MP3 bitrate</p>",
            unsafe_allow_html=True,
        )
    with bitrate_select_col:
        bitrate = st.selectbox(
            "MP3 bitrate",
            ["128k", "192k", "256k", "320k"],
            index=0,
            label_visibility="collapsed",
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
    for col, name, precondition_state in zip(step_cols, STEPS, STEP_PRECONDITION_STATES):
        with col:
            container_key = f"step_card_{name.lower()}"
            with st.container(key=container_key, border=False):
                label_placeholder = st.empty()
                eligible = count_tracks_in_state(precondition_state) > 0
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
        try:
            results = get_youtube_search_results(search_string)
            video_id = find_best_matching_youtube_id(db_entry=row, search_results=results)
        except NoMatchingYoutubeVideoFoundError:
            row["State"] = STATE_NO_MATCH
        else:
            row[COLUMN_YOUTUBE_ID] = video_id
            row["State"] = STATE_MATCHED
        render_tracks()


def run_download_stage(download_dir):
    pending_rows = [row for row in st.session_state.tracks if row["State"] == STATE_MATCHED]
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
            if any(
                os.path.exists(os.path.join(download_dir, song_filename + ext))
                for ext in SUPPORTED_FORMATS
            ):
                row["State"] = STATE_DOWNLOADED
            else:
                try:
                    youtube_url = get_youtube_url(row)
                    output_filepath = get_audio_from_youtube(
                        youtube_url=youtube_url, output_dir=download_dir, filename=song_filename
                    )
                    file_extension = os.path.splitext(output_filepath)[1]
                    metadata_tags = prepare_metadata_tags(
                        music_df_row=row,
                        file_extension=file_extension,
                        artist_in_title=artist_in_title,
                    )
                    set_file_metadata_tags(filepath=output_filepath, metadata_tags=metadata_tags)
                except BotDetection:
                    row["State"] = STATE_FAILED_BEFORE_RETRY
                    still_pending.append(row)
                except Exception:
                    row["State"] = STATE_FAILED
                else:
                    row["State"] = STATE_DOWNLOADED

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
        if row["State"] == STATE_DOWNLOADED
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
        else:
            if row is not None:
                row["State"] = STATE_CONVERTING
                render_tracks()
            success = convert_to_mp3(filepath, mp3_path, bitrate)
            if row is not None:
                row["State"] = STATE_CONVERTED if success else STATE_FAILED_CONVERTING
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
            data=[{k: row[k] for k in data_columns} for row in matched_rows if row.get(COLUMN_YOUTUBE_ID)],
            fieldnames=data_columns,
        )
        unmatched_rows = [row for row in st.session_state.tracks if row["State"] == STATE_NO_MATCH]
        if unmatched_rows:
            write_csv(
                file_path=os.path.join(download_dir, f"{playlist_name}_without_ids.csv"),
                data=[{k: row[k] for k in data_columns if k != COLUMN_YOUTUBE_ID} for row in unmatched_rows],
                fieldnames=[c for c in data_columns if c != COLUMN_YOUTUBE_ID],
            )
            st.warning(f"{len(unmatched_rows)} song(s) had no matching Youtube video.")

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
