import re

from pandas import read_csv
from pandas.core.series import Series

# Column names
COLUMN_ARTIST_NAME = "Artist Name(s)"
COLUMN_TRACK_NAME = "Track Name"
COLUMN_TRACK_DURATION_EXPORTIFY = "Track Duration (ms)"
COLUMN_TRACK_DURATION = "Duration (s)"
COLUMN_YOUTUBE_ID = "Youtube ID"


def get_pandas_df_from_exportify_csv(filepath: str):
    # Read CSV into a DataFrame
    df = read_csv(filepath)

    # Select only relevant columns
    columns_to_keep = [COLUMN_TRACK_NAME, COLUMN_ARTIST_NAME, COLUMN_TRACK_DURATION_EXPORTIFY]
    selected_df = df[columns_to_keep]

    # Rename and convert Duration column to seconds
    selected_df.loc[:, COLUMN_TRACK_DURATION_EXPORTIFY] = selected_df[COLUMN_TRACK_DURATION_EXPORTIFY] // 1000
    selected_df = selected_df.rename(columns={COLUMN_TRACK_DURATION_EXPORTIFY: COLUMN_TRACK_DURATION})

    # Ensure that commas have a trailing space and replace multiple whitespaces
    selected_df[COLUMN_ARTIST_NAME] = selected_df[COLUMN_ARTIST_NAME].apply(
        lambda x: re.sub("\s+", " ", x.replace(",", ", "))
    )

    return selected_df


def get_song_filename(music_df_row: Series) -> str:
    return f"{music_df_row[COLUMN_ARTIST_NAME]} - {music_df_row[COLUMN_TRACK_NAME]}"


def get_youtube_url(music_df_row: Series) -> str:
    return f"https://www.youtube.com/watch?v={music_df_row[COLUMN_YOUTUBE_ID]}"
