#!/bin/bash

# Check if the input file argument is provided
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <input_file>"
    exit 1
fi

# Get the input file argument
input_file="$1"

# Generate the output file based on the input file
output_file="${input_file%.csv}_with_ids.csv"

# Get the download directory (same as input file, without .csv)
download_dir="${input_file%.csv}"

# Run the scripts one after the other
poetry run python create_db_with_youtube_ids.py "$input_file" && \
poetry run python download_tracks.py "$output_file" && \
poetry run python convert_tracks_to_mp3.py "$download_dir" -d
