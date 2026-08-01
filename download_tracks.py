"""This script takes the previously generated csv with youtube IDs and downloads the songs."""
import argparse
import os
import random
import sys
import time

from pytubefix.exceptions import BotDetection
from tqdm import tqdm

from src.data_handling import (
    get_data_list_from_csv_with_ids,
    get_song_filename,
    get_youtube_url,
)
from src.file_metadata import (
    SUPPORTED_FORMATS,
    prepare_metadata_tags,
    set_file_metadata_tags,
)
from src.youtube_download import get_audio_from_youtube

MAX_BOT_DETECTION_RETRIES = 3
RETRY_BACKOFF_BASE_SECONDS = 5


def _download_and_tag(row: dict, download_dir: str, artist_in_title: bool) -> None:
    """Download one track and write its metadata tags. Raises BotDetection on transient
    bot-detection failures so the caller can retry it in a later round."""
    song_filename = get_song_filename(row)
    youtube_url = get_youtube_url(row)
    output_filepath = get_audio_from_youtube(
        youtube_url=youtube_url, output_dir=download_dir, filename=song_filename
    )
    file_extension = os.path.splitext(output_filepath)[1]
    metadata_tags = prepare_metadata_tags(
        music_df_row=row, file_extension=file_extension, artist_in_title=artist_in_title
    )
    set_file_metadata_tags(filepath=output_filepath, metadata_tags=metadata_tags)


def main():
    """Read the provided CSV with Youtube IDs and attempt to download the songs."""
    # Arg parsing
    parser = argparse.ArgumentParser(
        description="Script to download audio from youtube videos."
    )

    parser.add_argument(
        "file_path", help="Path to a CSV file with the Youtube IDs", type=str
    )
    
    parser.add_argument(
        "--ait", "--artist-in-title", 
        action="store_true", 
        help="Include artist name in track title metadata (format: 'ARTIST - TRACK TITLE')"
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
    pending_rows = get_data_list_from_csv_with_ids(input_filepath)

    for retry_round in range(MAX_BOT_DETECTION_RETRIES + 1):
        if not pending_rows:
            break

        if retry_round > 0:
            delay = RETRY_BACKOFF_BASE_SECONDS * (2 ** (retry_round - 1)) + random.uniform(0, 1)
            print(
                f"\nRetrying {len(pending_rows)} track(s) that hit bot detection, "
                f"waiting {delay:.1f}s before retry round {retry_round}/{MAX_BOT_DETECTION_RETRIES}..."
            )
            time.sleep(delay)

        still_pending = []
        for row in tqdm(pending_rows, desc=f"Round {retry_round + 1}"):
            song_filename = get_song_filename(row)
            # Skip the track if it was already downloaded in a previous run
            if any(
                os.path.exists(os.path.join(download_dir, song_filename + ext))
                for ext in SUPPORTED_FORMATS
            ):
                print(f"Skipping '{song_filename}', already downloaded.")
                continue

            try:
                _download_and_tag(row, download_dir, args.ait)
            except BotDetection:
                still_pending.append(row)
            except Exception as error:
                print(f"Error downloading {song_filename}: {error}")
        pending_rows = still_pending

    if pending_rows:
        song_names = ", ".join(get_song_filename(row) for row in pending_rows)
        print(f"\n{len(pending_rows)} track(s) failed after repeated bot detection: {song_names}")

    print("Successfully finished song downloads.\n")


if __name__ == "__main__":
    main()
