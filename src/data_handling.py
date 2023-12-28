import re

from pandas import read_csv
from pandas.core.series import Series
from pandas.core.indexes.base import Index

# Column names
COLUMN_ARTIST_NAME = "Artist Name(s)"
COLUMN_TRACK_NAME = "Track Name"
COLUMN_TRACK_DURATION = "Duration (s)"
COLUMN_YOUTUBE_ID = "Youtube ID"
COLUMN_TRACK_DURATION_EXPORTIFY_ALTERNATIVES = {"Track Duration (ms)", "Duration (ms)"}


class TrackDurationColumnNameNotFoundError(Exception):
    """Exception raised when none of the known column names for the track duration matches"""


def get_pandas_df_from_exportify_csv(filepath: str):
    # Read CSV into a DataFrame
    df = read_csv(filepath)

    # Find the track duration column name
    track_duration_column = _get_track_duration_column_name(df.columns)

    # Select only relevant columns
    columns_to_keep = [COLUMN_TRACK_NAME, COLUMN_ARTIST_NAME, track_duration_column]
    selected_df = df[columns_to_keep]

    # Rename and convert Duration column to seconds
    selected_df.loc[:, track_duration_column] = selected_df[track_duration_column] // 1000
    selected_df = selected_df.rename(columns={track_duration_column: COLUMN_TRACK_DURATION})

    # Ensure that commas have a trailing space and replace multiple whitespaces
    selected_df[COLUMN_ARTIST_NAME] = selected_df[COLUMN_ARTIST_NAME].apply(
        lambda x: re.sub("\s+", " ", x.replace(",", ", "))
    )

    return selected_df


def _get_track_duration_column_name(df_columns: Index) -> str:
    for column_name in COLUMN_TRACK_DURATION_EXPORTIFY_ALTERNATIVES:
        if column_name in df_columns:
            return column_name
    raise TrackDurationColumnNameNotFoundError("Unable to find the Track Duration column")


def get_song_filename(music_df_row: Series) -> str:
    return f"{music_df_row[COLUMN_ARTIST_NAME]} - {music_df_row[COLUMN_TRACK_NAME]}"


def get_youtube_url(music_df_row: Series) -> str:
    return f"https://www.youtube.com/watch?v={music_df_row[COLUMN_YOUTUBE_ID]}"
