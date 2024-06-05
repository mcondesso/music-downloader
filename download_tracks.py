"""This script takes the previously generated csv with youtube IDs and downloads the songs."""
import argparse
import os
import sys

from tqdm import tqdm

from src.data_handling import (
    get_data_list_from_csv_with_ids,
    get_song_filename,
    get_youtube_url,
)
from src.file_metadata import prepare_metadata_tags, set_file_metadata_tags
from src.youtube_download import get_audio_from_youtube


def main():
    """Read the provided CSV with Youtube IDs and attempt to download the songs."""
    # Arg parsing
    parser = argparse.ArgumentParser(
        description="Script to download audio from youtube videos."
    )

    parser.add_argument(
        "file_path", help="Path to a CSV file with the Youtube IDs", type=str
    )

    args = parser.parse_args()
    if not args.file_path:
        print("Use -f to specify the path to the CSV file.")
        sys.exit(1)
    else:
        input_filepath = args.file_path

    # Create directory with the same name as the input file,
    # this is the destination folder for the downloads
    input_song_list_file, _ = os.path.splitext(input_filepath)
    download_dir = input_song_list_file.removesuffix("_with_ids")
    os.makedirs(download_dir, exist_ok=True)

    print("Starting downloads into ", download_dir)

    # Read CSV file
    music_df = get_data_list_from_csv_with_ids(input_filepath)

    for row in tqdm(music_df):
        song_filename = get_song_filename(row)
        youtube_url = get_youtube_url(row)

        # Download audio track
        try:
            output_filepath = get_audio_from_youtube(
                youtube_url=youtube_url, output_dir=download_dir, filename=song_filename
            )
        except Exception as error:
            print(f"Error downloading {song_filename}: {error}")
            continue

        # Set Metadata Tags for song title and artist
        file_extension = os.path.splitext(output_filepath)[1]
        metadata_tags = prepare_metadata_tags(
            music_df_row=row, file_extension=file_extension
        )
        set_file_metadata_tags(filepath=output_filepath, metadata_tags=metadata_tags)

    print("Successfully finished song downloads.\n")


if __name__ == "__main__":
    main()
