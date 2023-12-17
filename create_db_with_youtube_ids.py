import argparse
import os

from tqdm import tqdm

from src.data_handling import (
    get_pandas_df_from_exportify_csv,
    get_song_filename,
    COLUMN_YOUTUBE_ID,
)
from src.youtube_search import (
    get_youtube_search_results,
    NoMatchingYoutubeVideoFoundError,
    find_best_matching_youtube_id,
)


def get_output_filename(input_filename: str) -> str:
    # Split the path into directory and file components
    directory, file_name = os.path.split(input_filename)

    # Split the file name into name and extension
    name, extension = os.path.splitext(file_name)

    # Construct the modified path by appending "with_ids" before the extension
    modified_path = os.path.join(directory, f"{name}_with_ids{extension}")

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

    for index, row in tqdm(music_df.iterrows()):
        search_string = get_song_filename(row)
        search_results = get_youtube_search_results(search_string)
        try:
            video_id = find_best_matching_youtube_id(
                db_entry=row, search_results=search_results
            )
        except NoMatchingYoutubeVideoFoundError as error:
            print(error)
        else:
            music_df.at[index, COLUMN_YOUTUBE_ID] = video_id

    output_filename = get_output_filename(input_filepath)
    music_df.to_csv(output_filename, index=False)

    print(f"Created {output_filename}.\n")


if __name__ == "__main__":
    main()
