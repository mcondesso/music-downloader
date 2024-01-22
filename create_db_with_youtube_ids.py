import argparse
import os

from tqdm import tqdm

from src.data_handling import (
    COLUMN_YOUTUBE_ID,
    get_data_list_from_exportify_csv,
    get_song_filename,
    write_csv,
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
    music_df, column_names = get_data_list_from_exportify_csv(filepath=input_filepath)

    print("Finding Youtube IDs for the songs...")

    row_list_with_ids = list()
    row_list_missing_ids = list()

    for row in tqdm(music_df):
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
    write_csv(
        file_path=filename_with_ids,
        data=row_list_with_ids,
        fieldnames=column_names + [COLUMN_YOUTUBE_ID],
    )

    if row_list_missing_ids:
        filename_without_ids = get_output_filename(input_filepath, with_ids=False)
        write_csv(
            file_path=filename_without_ids,
            data=row_list_missing_ids,
            fieldnames=column_names,
        )


if __name__ == "__main__":
    main()
