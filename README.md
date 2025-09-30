# Music downloader

## Main Workflow

The main workflow is automated via the `run.sh` script:

```
./run.sh <path_to_file_extracted_by_exportify.csv>
```

This will:
1. Generate a new CSV with Youtube IDs for each song (`create_db_with_youtube_ids.py`).
2. Download the tracks from Youtube (`download_tracks.py`).
3. Convert all downloaded tracks to MP3 format (`convert_tracks_to_mp3.py`).

All downloaded files will be saved as MP3 in a folder named after your input file (without `.csv`).

---

## Individual Scripts

* `create_db_with_youtube_ids.py` takes a CSV file with song data from Exportify as input and creates a new CSV containing:
    * For each song, we store "Track Name", "Artist Name(s)", "Duration (ms)", as well as a likely corresponding "Youtube ID".
* `download_tracks.py` takes the CSV created by the previous step as input and downloads the songs from the matched youtube video.
    * After the download, the `Title` and `Contributing Artists` are set into the file's metadata tags.
* `convert_tracks_to_mp3.py` converts all audio files in a directory to MP3 format (128kbps by default), preserving metadata. Use:
    * `poetry run python convert_tracks_to_mp3.py <download_folder> [-d]`
    * The `-d` flag deletes original files after conversion.

---

## Directory Scanning: create_db_from_directory.py

If you have a folder of music files and want to generate a CSV database from their metadata:

* `create_db_from_directory.py` scans a directory for audio files and creates a CSV DB with columns:
    * Artist Name(s), Track Name, Duration (s), Genres, Tempo, Absolute Filepath, Bit rate, Youtube ID
* Usage:
    * `poetry run python create_db_from_directory.py <music_folder>`

## Setup and Run
## Setup

1. [Install poetry](https://python-poetry.org/docs/#installing-with-the-official-installer) for package management
2. `poetry install`
