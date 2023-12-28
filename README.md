# Music downloader

There are two scripts:
* `create_db_with_youtube_ids` takes a CSV file with song data from Exportify as input and creates a new CSV containing.
    * For each song, we store "Track Name", "Artist Name(s)", "Duration (ms)", as well as a likely corresponding "Youtube ID"
* `download_tracks` takes the CSV created by the previous step as input and downloads the songs from the matched youtube video
    * After the download, the `Title` and `Contributing Artists` are set into the file's metadata tags.

## Setup and Run
Setup the virtual environment:
* [Install poetry](https://python-poetry.org/docs/#installing-with-the-official-installer) for package management
* `poetry install`

In order to run the scripts, you can run the bash script `run.sh <path_to_file_extracted_by_exportify.csv>`

Alternatively, you can run the two python scripts individually
* `poetry run python create_db_with_youtube_ids.py <path_to_file_extracted_by_exportify.csv>`
* `poetry run python download_tracks.py <path_to_file_created_by_previous_script.csv>`
