import argparse
import os

from pandas import DataFrame
from tqdm import tqdm

from src.data_handling import (
    COLUMN_YOUTUBE_ID,
    get_pandas_df_from_exportify_csv,
    get_song_filename,
)
from src.youtube_search import (
    NoMatchingYoutubeVideoFoundError,
    find_best_matching_youtube_id,
    get_youtube_search_results,
)


def get_output_filename(input_filename: str, with_ids: bool) -> str:
    # Split the path into directory and file components
    directory, file_name = os.path.split(input_filename)

    # Split the file name into name and extension
    name, extension = os.path.splitext(file_name)

    # Construct the modified filepath
    ids = "with_ids" if with_ids else "without_ids"
    modified_path = os.path.join(directory, f"{name}_{ids}{extension}")

    return modified_path


def main():
    # Arg parsing
    parser = argparse.ArgumentParser(
        description="Script to find Youtube IDs from an Exportify CSV."
    )

    parser.add_argument("file_path", help="Path to a CSV file from Exportify", type=str)

    args = parser.parse_args()
    if not args.file_path:
        print("Use -f to specify the path to the CSV file.")
        exit(1)
    else:
        input_filepath = args.file_path

    # Read CSV file
    music_df = get_pandas_df_from_exportify_csv(filepath=input_filepath)

    # Add new empty column to receive the Youtube IDs
    music_df[COLUMN_YOUTUBE_ID] = ""

    print("Finding Youtube IDs for the songs...")

    row_list_with_ids = list()
    row_list_missing_ids = list()

    for index, row in tqdm(music_df.iterrows()):
        search_string = get_song_filename(row)
        search_results = get_youtube_search_results(search_string)
        try:
            video_id = find_best_matching_youtube_id(
                db_entry=row, search_results=search_results
            )
        except NoMatchingYoutubeVideoFoundError as error:
            print(error)
            row_list_missing_ids.append(row)
        else:
            row[COLUMN_YOUTUBE_ID] = video_id
            row_list_with_ids.append(row)

    filename_with_ids = get_output_filename(input_filepath, with_ids=True)
    music_df_with_ids = DataFrame(row_list_with_ids)
    music_df_with_ids.to_csv(filename_with_ids, index=False)
    print(f"Created {filename_with_ids}.\n")

    if row_list_missing_ids:
        filename_without_ids = get_output_filename(input_filepath, with_ids=False)
        music_df_without_ids = DataFrame(row_list_missing_ids)
        music_df_without_ids.to_csv(filename_without_ids, index=False)
        print(f"Created {filename_without_ids}.\n")


if __name__ == "__main__":
    main()
