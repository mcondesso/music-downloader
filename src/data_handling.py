"""Module for handling file reading and writing data files."""
import re
from typing import Dict, List, Tuple

from src.csv_handling import read_csv

# Column names
COLUMN_ARTIST_NAME = "Artist Name(s)"
COLUMN_TRACK_NAME = "Track Name"
REQUIRED_COLUMNS = [COLUMN_ARTIST_NAME, COLUMN_TRACK_NAME]
COLUMN_TRACK_DURATION_EXPORTIFY_ALTERNATIVES = {"Track Duration (ms)", "Duration (ms)"}
COLUMN_GENRES = "Genres"
COLUMN_TEMPO = "Tempo"
COLUMN_TRACK_DURATION = "Duration (s)"
COLUMN_YOUTUBE_ID = "Youtube ID"


class RequiredColumnNameNotFoundError(Exception):
    """Exception raised when one of the required column names is missing"""


class TrackDurationColumnNameNotFoundError(RequiredColumnNameNotFoundError):
    """Exception raised when none of the known column names for the track duration matches"""


def get_data_list_from_exportify_csv(filepath: str) -> Tuple[List[dict], List[str]]:
    """This function loads, validates and standardizes data
    from a CSV file obtained via Exportify."""
    # Read full CSV into a list of dicts and extract column names
    data, total_colnames = read_csv(filepath)

    # Find column with Track Duration
    track_duration_col = _get_track_duration_column_name(total_colnames)

    # Validate that other required columns are present
    for col in REQUIRED_COLUMNS:
        if col not in total_colnames:
            raise RequiredColumnNameNotFoundError(f"Column '{col}' is missing")

    # Select only relevant columns
    column_names = REQUIRED_COLUMNS + [
        track_duration_col,
        COLUMN_GENRES,
        COLUMN_TEMPO,
    ]

    selected_df = []
    for row in data:
        # Copy over the selected columns
        selected_row = {key: row[key] for key in column_names}

        # Rename and convert Duration column to seconds
        selected_row[COLUMN_TRACK_DURATION] = (
            int(selected_row.pop(track_duration_col)) // 1000
        )

        # Ensure that commas have a trailing space and replace multiple whitespaces
        artist_name = selected_row[COLUMN_ARTIST_NAME].replace(",", ", ")
        selected_row[COLUMN_ARTIST_NAME] = re.sub(r"\s+", " ", artist_name)

        selected_df.append(selected_row)

    final_column_names = REQUIRED_COLUMNS + [
        COLUMN_TRACK_DURATION,
        COLUMN_GENRES,
        COLUMN_TEMPO,
    ]

    return selected_df, final_column_names


def get_data_list_from_csv_with_ids(filepath: str) -> List[dict]:
    """This function loads and validates data from a file with the song youtube IDs."""
    # Read full CSV into a list of dicts and extract column names
    data, total_colnames = read_csv(filepath)

    # Validate that other required columns are present
    for col in REQUIRED_COLUMNS + [COLUMN_TRACK_DURATION, COLUMN_YOUTUBE_ID]:
        if col not in total_colnames:
            raise RequiredColumnNameNotFoundError(f"Column '{col}' is missing")

    return data


def _get_track_duration_column_name(field_names: List) -> str:
    """This function is used to figure out which column name from exportify
    contains the track duration data"""
    for column_name in COLUMN_TRACK_DURATION_EXPORTIFY_ALTERNATIVES:
        if column_name in field_names:
            return column_name
    raise TrackDurationColumnNameNotFoundError(
        "Unable to find the Track Duration column"
    )


def get_song_search_string(music_row: Dict) -> str:
    """Helper function to generate the search string a song."""
    return f"{music_row[COLUMN_ARTIST_NAME]} - {music_row[COLUMN_TRACK_NAME]}"


def get_youtube_url(music_row: Dict) -> str:
    """Helper function to generate the youtube URL for a song."""
    return f"https://www.youtube.com/watch?v={music_row[COLUMN_YOUTUBE_ID]}"


def get_song_filename(music_row: Dict) -> str:
    """Helper function to generate the filename for a song,
    escaping slashes."""
    search_string = get_song_search_string(music_row=music_row)
    return sanitize_filename(search_string)


def sanitize_filename(filename: str) -> str:
    """Replaces invalid chars in filenames with underscores."""
    invalid_chars = r'\/:*?"<>|'
    translation_table = str.maketrans(invalid_chars, "_" * len(invalid_chars))
    sanitized = filename.translate(translation_table)
    return sanitized
