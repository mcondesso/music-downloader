"""Module for handling file metadata for the supported file types."""
import os
from typing import Dict

from mutagen.easyid3 import EasyID3
from mutagen.mp4 import MP4

from src.data_handling import COLUMN_ARTIST_NAME, COLUMN_TRACK_NAME

FILE_EXTENSION_MP3 = ".mp3"
FILE_EXTENSION_MP4 = ".mp4"

SUPPORTED_FORMATS = {FILE_EXTENSION_MP3, FILE_EXTENSION_MP4}

METADATA_TAGS = {
    FILE_EXTENSION_MP3: {
        "artist": "artist",
        "title": "title",
    },
    FILE_EXTENSION_MP4: {
        "artist": "©ART",
        "title": "©nam",
    },
}

METADATA_CLASSES = {
    FILE_EXTENSION_MP3: EasyID3,
    FILE_EXTENSION_MP4: MP4,
}


def prepare_metadata_tags(music_df_row: Dict, file_extension: str) -> dict:
    """This function prepares the metadata tags to be written onto a
    music file, depending on the file format."""
    artist_tag = METADATA_TAGS[file_extension]["artist"]
    title_tag = METADATA_TAGS[file_extension]["title"]

    if file_extension == FILE_EXTENSION_MP4:
        # .mp4 files do not support a list of values for Contributing Artist
        # So we have to provide them as a single string, see
        # https://github.com/quodlibet/mutagen/issues/548
        artist_names = music_df_row[COLUMN_ARTIST_NAME]
    else:
        artist_names = music_df_row[COLUMN_ARTIST_NAME].split(",")

    return {
        artist_tag: artist_names,
        title_tag: music_df_row[COLUMN_TRACK_NAME],
    }


def set_file_metadata_tags(filepath: str, metadata_tags: dict):
    """This function sets the provided metadata tags onto a file."""
    file_extension = os.path.splitext(filepath)[1]
    tag_handling_class = METADATA_CLASSES[file_extension]
    tag_dict = tag_handling_class(filepath)
    for key, value in metadata_tags.items():
        tag_dict[key] = value
    tag_dict.save()
