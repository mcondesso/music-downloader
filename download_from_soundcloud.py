"""Script to download tracks directly from SoundCloud track URLs."""
import argparse
import os
import sys

from src.data_handling import (
    COLUMN_ARTIST_NAME,
    COLUMN_TRACK_NAME,
    sanitize_filename,
)
from src.file_metadata import (
    SUPPORTED_FORMATS,
    prepare_metadata_tags,
    set_file_metadata_tags,
)
from src.soundcloud_download import (
    get_audio_from_soundcloud,
    get_soundcloud_track_info,
)

DEFAULT_OUTPUT_DIR = "soundcloud_downloads"


def main():
    """Download each provided SoundCloud track URL and write metadata tags."""
    parser = argparse.ArgumentParser(
        description="Script to download audio tracks from SoundCloud URLs."
    )
    parser.add_argument(
        "urls", nargs="+", help="One or more SoundCloud track URLs", type=str
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Destination folder for the downloads (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--ait",
        "--artist-in-title",
        action="store_true",
        help="Include artist name in track title metadata (format: 'ARTIST - TRACK TITLE')",
    )
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    print("Starting downloads into ", args.output_dir)

    n_errors = 0
    for url in args.urls:
        try:
            track_info = get_soundcloud_track_info(url)
            music_df_row = {
                COLUMN_ARTIST_NAME: track_info["artist"],
                COLUMN_TRACK_NAME: track_info["track"],
            }
            song_filename = sanitize_filename(
                f"{track_info['artist']} - {track_info['track']}"
            )

            # Skip the track if it was already downloaded in a previous run
            if any(
                os.path.exists(os.path.join(args.output_dir, song_filename + ext))
                for ext in SUPPORTED_FORMATS
            ):
                print(f"Skipping '{song_filename}', already downloaded.")
                continue

            output_filepath = get_audio_from_soundcloud(
                soundcloud_url=url,
                output_dir=args.output_dir,
                filename=song_filename,
            )
            file_extension = os.path.splitext(output_filepath)[1]
            metadata_tags = prepare_metadata_tags(
                music_df_row=music_df_row,
                file_extension=file_extension,
                artist_in_title=args.ait,
            )
            set_file_metadata_tags(
                filepath=output_filepath, metadata_tags=metadata_tags
            )
        except Exception as error:
            n_errors += 1
            print(f"Error downloading {url}: {error}")

    print("Successfully finished song downloads.\n")
    if n_errors:
        print(f"{n_errors} download(s) failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
