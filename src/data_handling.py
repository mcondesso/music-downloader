import re

from pandas import read_csv
from pandas.core.series import Series


def get_pandas_df_from_exportify_csv(filepath: str):
    # Read CSV into a DataFrame
    df = read_csv(filepath)

    # Select only relevant columns
    columns_to_keep = ["Track Name", "Artist Name(s)", "Duration (ms)"]
    selected_df = df[columns_to_keep]

    # Rename and convert Duration column to seconds
    selected_df.loc[:, "Duration (ms)"] = selected_df["Duration (ms)"] // 1000
    selected_df = selected_df.rename(columns={"Duration (ms)": "Duration (s)"})

    # Ensure that commas have a trailing space and replace multiple whitespaces
    selected_df["Artist Name(s)"] = selected_df["Artist Name(s)"].apply(
        lambda x: re.sub("\s+", " ", x.replace(",", ", "))
    )

    return selected_df


def get_song_filename(music_df_row: Series) -> str:
    return f"{music_df_row['Artist Name(s)']} - {music_df_row['Track Name']}"


def get_youtube_url(music_df_row: Series) -> str:
    return f"https://www.youtube.com/watch?v={music_df_row['Youtube ID']}"
