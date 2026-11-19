#!/bin/bash

usage() {
    echo "Usage: $0 [--mp3] <input_file>"
    echo "  --mp3  Also convert the downloaded .m4a files to MP3 and delete the originals."
    echo "         Off by default: the downloads are already AAC, so converting to MP3 is"
    echo "         a second lossy encode. Use it only for players that can't play .m4a."
    exit 1
}

convert_to_mp3=false
if [ "$1" = "--mp3" ]; then
    convert_to_mp3=true
    shift
fi

# Check if the input file argument is provided
if [ "$#" -ne 1 ]; then
    usage
fi

# Get the input file argument
input_file="$1"

# Generate the output file based on the input file
output_file="${input_file%.csv}_with_ids.csv"

# Get the download directory (same as input file, without .csv)
download_dir="${input_file%.csv}"

# Run the scripts one after the other
poetry run python create_db_with_youtube_ids.py "$input_file" && \
poetry run python download_tracks.py "$output_file" || exit $?

if [ "$convert_to_mp3" = true ]; then
    poetry run python convert_tracks_to_mp3.py "$download_dir" -d
fi
