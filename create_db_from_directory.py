"""
This script scans a directory for audio files and creates a CSV DB with metadata for each file.
"""

import argparse
import os
import sys
from tqdm import tqdm
from src.csv_handling import write_csv
from src.data_handling import (
    COLUMN_ARTIST_NAME,
    COLUMN_TRACK_NAME,
    COLUMN_TRACK_DURATION,
    COLUMN_GENRES,
    COLUMN_TEMPO,
    COLUMN_ABSOLUTE_FILEPATH,
    COLUMN_BIT_RATE,
    COLUMN_YOUTUBE_ID,
    get_song_search_string,
)
from src.youtube_id_search import (
    NoMatchingYoutubeVideoFoundError,
    find_best_matching_youtube_id,
    get_youtube_search_results,
)
from src.file_metadata import extract_metadata_from_file


def get_output_filename(directory: str) -> str:
    """Generate output filename for the CSV DB."""
    directory = os.path.abspath(directory)
    name = os.path.basename(directory.rstrip(os.sep))
    return os.path.join(directory, f"{name}_db.csv")


def scan_directory_for_audio_files(directory: str):
    """Recursively scan directory for audio files."""
    audio_extensions = {".mp3", ".mp4"}
    for root, _, files in os.walk(directory):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in audio_extensions:
                yield os.path.join(root, file)


def main():
    """
    Scans a directory recursively for audio files, extracts metadata, and writes a CSV DB.
    Columns: Artist Name(s), Track Name, Duration (s), Genres, Tempo, absolute-filepath
    """
    parser = argparse.ArgumentParser(
        description="Scan a directory for audio files and create a CSV DB with metadata."
    )
    parser.add_argument("directory", help="Path to the directory to scan", type=str)
    args = parser.parse_args()
    if not args.directory or not os.path.isdir(args.directory):
        print("Please provide a valid directory path.")
        sys.exit(1)
    directory = args.directory
    print(f"Scanning directory: {directory}")
    audio_files = list(scan_directory_for_audio_files(directory))
    print(f"Found {len(audio_files)} audio files.")
    rows = []
    for filepath in tqdm(audio_files):
        metadata = extract_metadata_from_file(filepath)
        bit_rate = metadata.get("bit_rate", "")
        if not bit_rate:
            bit_rate = "0"
        row = {
            COLUMN_ARTIST_NAME: metadata.get("artist", ""),
            COLUMN_TRACK_NAME: metadata.get("title", ""),
            COLUMN_TRACK_DURATION: metadata.get("duration", 0),
            COLUMN_GENRES: metadata.get("genres", ""),
            COLUMN_TEMPO: metadata.get("tempo", ""),
            COLUMN_ABSOLUTE_FILEPATH: f"{os.path.abspath(filepath)}",
            COLUMN_BIT_RATE: bit_rate,
        }
        # Youtube ID search
        search_string = get_song_search_string(row)
        search_results = get_youtube_search_results(search_string)
        try:
            video_id = find_best_matching_youtube_id(
                db_entry=row, search_results=search_results
            )
        except NoMatchingYoutubeVideoFoundError:
            video_id = ""
        row[COLUMN_YOUTUBE_ID] = video_id
        rows.append(row)
    fieldnames = [
        COLUMN_ARTIST_NAME,
        COLUMN_TRACK_NAME,
        COLUMN_TRACK_DURATION,
        COLUMN_GENRES,
        COLUMN_TEMPO,
        COLUMN_ABSOLUTE_FILEPATH,
        COLUMN_BIT_RATE,
        COLUMN_YOUTUBE_ID,
    ]
    output_filename = get_output_filename(directory)
    write_csv(
        file_path=output_filename,
        data=rows,
        fieldnames=fieldnames,
    )
    print(f"CSV DB written to: {output_filename}")


if __name__ == "__main__":
    main()
