"""Module for handling file metadata for the supported file types."""
import os
from typing import Dict

from mutagen.easyid3 import EasyID3
from mutagen.mp4 import MP4

from src.data_handling import (
    COLUMN_ARTIST_NAME,
    COLUMN_TRACK_NAME,
    COLUMN_GENRES,
    COLUMN_TEMPO,
    get_song_search_string,
)

FILE_EXTENSION_MP3 = ".mp3"
FILE_EXTENSION_MP4 = ".mp4"

SUPPORTED_FORMATS = {FILE_EXTENSION_MP3, FILE_EXTENSION_MP4}

METADATA_TAGS = {
    FILE_EXTENSION_MP3: {
        "artist": "artist",
        "title": "title",
        "genre": "genre",
        "tempo": "bpm",
    },
    FILE_EXTENSION_MP4: {
        "artist": "©ART",
        "title": "©nam",
        "genre": "©gen",
        "tempo": "tmpo",
    },
}

METADATA_CLASSES = {
    FILE_EXTENSION_MP3: EasyID3,
    FILE_EXTENSION_MP4: MP4,
}


def prepare_metadata_tags(music_df_row: Dict, file_extension: str, artist_in_title: bool = False) -> dict:
    """This function prepares the metadata tags to be written onto a
    music file, depending on the file format."""
    artist_tag = METADATA_TAGS[file_extension]["artist"]
    title_tag = METADATA_TAGS[file_extension]["title"]
    genre_tag = METADATA_TAGS[file_extension]["genre"]
    tempo_tag = METADATA_TAGS[file_extension]["tempo"]

    if file_extension == FILE_EXTENSION_MP4:
        artist_names = music_df_row[COLUMN_ARTIST_NAME].replace(", ", "/")
    else:
        artist_names = music_df_row[COLUMN_ARTIST_NAME].split(",")

    # Determine the title based on artist_in_title flag
    if artist_in_title:
        title = get_song_search_string(music_df_row)
    else:
        title = music_df_row[COLUMN_TRACK_NAME]

    return {
        artist_tag: artist_names,
        title_tag: title,
        genre_tag: music_df_row[COLUMN_GENRES],
        tempo_tag:  [round(float(music_df_row[COLUMN_TEMPO]))],
    }


def set_file_metadata_tags(filepath: str, metadata_tags: dict):
    """This function sets the provided metadata tags onto a file."""
    file_extension = os.path.splitext(filepath)[1]
    tag_handling_class = METADATA_CLASSES[file_extension]
    tag_dict = tag_handling_class(filepath)
    for key, value in metadata_tags.items():
        tag_dict[key] = value
    tag_dict.save()
