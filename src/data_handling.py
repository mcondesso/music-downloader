import re
from csv import DictReader, DictWriter
from typing import Dict, List, Tuple

# Column names
COLUMN_ARTIST_NAME = "Artist Name(s)"
COLUMN_TRACK_NAME = "Track Name"
REQUIRED_COLUMNS = [COLUMN_ARTIST_NAME, COLUMN_TRACK_NAME]
COLUMN_TRACK_DURATION_EXPORTIFY_ALTERNATIVES = {"Track Duration (ms)", "Duration (ms)"}
COLUMN_TRACK_DURATION = "Duration (s)"
COLUMN_YOUTUBE_ID = "Youtube ID"


class RequiredColumnNameNotFoundError(Exception):
    """Exception raised when one of the required column names is missing"""


class TrackDurationColumnNameNotFoundError(RequiredColumnNameNotFoundError):
    """Exception raised when none of the known column names for the track duration matches"""


def get_data_list_from_exportify_csv(filepath: str) -> Tuple[List[dict], List[str]]:
    # Read full CSV into a list of dicts and extract column names
    data, total_colnames = load_csv(filepath)

    # Find column with Track Duration
    track_duration_col = _get_track_duration_column_name(total_colnames)

    # Validate that other required columns are present
    for col in REQUIRED_COLUMNS:
        if col not in total_colnames:
            raise RequiredColumnNameNotFoundError(f"Column '{col}' is missing")

    # Select only relevant columns
    column_names = REQUIRED_COLUMNS + [track_duration_col]
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
        selected_row[COLUMN_ARTIST_NAME] = re.sub("\s+", " ", artist_name)

        selected_df.append(selected_row)

    final_column_names = REQUIRED_COLUMNS + [COLUMN_TRACK_DURATION]

    return selected_df, final_column_names


def get_data_list_from_csv_with_ids(filepath: str) -> List[dict]:
    # Read full CSV into a list of dicts and extract column names
    data, total_colnames = load_csv(filepath)

    # Validate that other required columns are present
    for col in REQUIRED_COLUMNS + [COLUMN_TRACK_DURATION, COLUMN_YOUTUBE_ID]:
        if col not in total_colnames:
            raise RequiredColumnNameNotFoundError(f"Column '{col}' is missing")

    return data


def load_csv(file_path: str) -> Tuple[List[dict], str]:
    data = []
    with open(file_path, "r") as file:
        csv_reader = DictReader(file)

        # Read data into list of dictionaries
        for row in csv_reader:
            data.append(dict(row))

    return data, csv_reader.fieldnames


def write_csv(file_path, data, fieldnames):
    with open(file_path, "w", newline="") as file:
        csv_writer = DictWriter(file, fieldnames=fieldnames)

        # Write the header
        csv_writer.writeheader()

        # Write the data
        csv_writer.writerows(data)
    print(f"Created {file_path}.\n")


def _get_track_duration_column_name(field_names: List) -> str:
    for column_name in COLUMN_TRACK_DURATION_EXPORTIFY_ALTERNATIVES:
        if column_name in field_names:
            return column_name
    raise TrackDurationColumnNameNotFoundError(
        "Unable to find the Track Duration column"
    )


def get_song_filename(music_row: Dict) -> str:
    return f"{music_row[COLUMN_ARTIST_NAME]} - {music_row[COLUMN_TRACK_NAME]}"


def get_youtube_url(music_row: Dict) -> str:
    return f"https://www.youtube.com/watch?v={music_row[COLUMN_YOUTUBE_ID]}"
