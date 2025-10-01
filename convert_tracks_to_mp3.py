"""
Script to convert all audio files in a directory (recursively) to MP3 format using ffmpeg and the
LAME encoder. Only files not already in MP3 format will be converted.
"""

import argparse
import os
import subprocess
from tqdm import tqdm
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.easyid3 import EasyID3
from src.file_metadata import (
    extract_metadata_from_file,
    prepare_metadata_tags,
    set_file_metadata_tags,
    FILE_EXTENSION_MP3,
    FILE_EXTENSION_MP4,
)
from src.file_handling import scan_directory_for_audio_files


def convert_to_mp3(input_path, output_path, bitrate="128k"):
    """
    Convert an audio file to MP3 format using ffmpeg and the LAME encoder.
    Overwrites output if it exists.
    """
    cmd = [
        "ffmpeg",
        "-y",  # overwrite output
        "-i",
        input_path,
        "-codec:a",
        "libmp3lame",
        "-b:a",
        bitrate,
        output_path,
    ]
    subprocess.run(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True
    )
    ext = os.path.splitext(input_path)[1].lower()
    try:
        if ext == FILE_EXTENSION_MP4:
            metadata = extract_metadata_from_file(input_path)
            music_df_row = {
                "Artist Name(s)": metadata.get("artist", ""),
                "Track Name": metadata.get("title", ""),
                "Genres": metadata.get("genres", ""),
                "Tempo": metadata.get("tempo", ""),
            }
            tags = prepare_metadata_tags(music_df_row, FILE_EXTENSION_MP3)
            set_file_metadata_tags(output_path, tags)
    except Exception as e:
        print(
            f"Warning: Could not copy metadata from {input_path} to {output_path}: {e}"
        )


def main():
    """
    Converts all non-MP3 audio files in a directory to MP3 format (default: 128kbps).
    Skips files that are already in MP3 format or if an MP3 version exists.
    """
    parser = argparse.ArgumentParser(
        description="Convert all audio files in a directory to MP3 format."
    )
    parser.add_argument(
        "directory",
        help="Path to the directory to scan",
        type=str,
    )
    parser.add_argument(
        "--bitrate",
        help="MP3 bitrate (default: 128k)",
        default="128k",
    )
    parser.add_argument(
        "-d",
        "--delete-originals",
        action="store_true",
        help="Delete original files after conversion.",
    )
    args = parser.parse_args()
    directory = args.directory
    bitrate = args.bitrate
    delete_originals = args.delete_originals
    print(f"Scanning directory: {directory}")
    audio_files = list(scan_directory_for_audio_files(directory, {FILE_EXTENSION_MP4}))
    print(f"Found {len(audio_files)} non-MP3 audio files.")
    for filepath in tqdm(audio_files):
        song_filename = os.path.basename(filepath)
        print(f"\nConverting: {song_filename}")
        mp3_path = os.path.splitext(filepath)[0] + ".mp3"
        if os.path.exists(mp3_path):
            continue  # Skip if MP3 already exists
        convert_to_mp3(filepath, mp3_path, bitrate)
        if delete_originals:
            try:
                os.remove(filepath)
            except Exception as e:
                print(f"Failed to delete {filepath}: {e}")
    print("Conversion complete.")


if __name__ == "__main__":
    main()
