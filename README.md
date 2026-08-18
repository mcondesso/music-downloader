# Track Tracker

## Web UI

Run the whole workflow from a browser:

```
poetry run streamlit run app.py
```

Then point it at an Exportify CSV (or a CSV that already has a "Youtube ID" column)
and click Start. Matching, downloading and MP3 conversion run one after another,
with progress bars and logs for each stage.

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
* `check_hardware_compat.py` checks audio files for compatibility with hardware DJ players (Pioneer/AlphaTheta CDJ/XDJ and similar) and reports a fix for each problem it finds — fragmented MP4 downloads, unsupported codecs (HE-AAC, Opus, ALAC), out-of-range sample rates, and WAV header traps. Use:
    * `poetry run python check_hardware_compat.py <file_or_folder>` (add `--all` to also list passing files)

---

## SoundCloud: download_from_soundcloud.py

To download tracks directly from SoundCloud track URLs (no CSV needed):

```
poetry run python download_from_soundcloud.py <url> [<url> ...] [-o <output_folder>] [--ait]
```

* Metadata (artist/track) is derived from the SoundCloud title (`Artist - Track`
  when the title contains a dash, otherwise the uploader is used as the artist)
  and written into the file's tags, like `download_tracks.py` does.
* Files are saved as `.mp3` — SoundCloud's native progressive stream, kept
  without transcoding (the same downloader the webapp uses).
* Already-downloaded tracks are skipped, matching the behaviour of
  `download_tracks.py`.
* Downloading only works for tracks whose owners allow streaming (tracks with
  a progressive stream); use it only where you have the rights to do so.

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
3. `sudo apt-get install ffmpeg` to be able run `convert_tracks_to_mp3.py`
