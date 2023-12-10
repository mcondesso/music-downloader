import os

from mutagen.easyid3 import EasyID3
from mutagen.mp4 import MP4
from pandas.core.series import Series

SUPPORTED_FORMATS = {".mp3", ".mp4"}

METADATA_TAGS = {
    ".mp3": {
        "artist": "artist",
        "title": "title",
    },
    ".mp4": {
        "artist": "©ART",
        "title": "©nam",
    },
}

METADATA_CLASSES = {
    ".mp3": EasyID3,
    ".mp4": MP4,
}

import pdb


def prepare_metadata_tags(music_df_row: Series, file_extension: str) -> dict:
    artist_tag = METADATA_TAGS[file_extension]["artist"]
    title_tag = METADATA_TAGS[file_extension]["title"]

    if file_extension == ".mp4":
        # .mp4 files do not support a list of values for Contributing Artist
        # So we have to provide them as a single string, see
        # https://github.com/quodlibet/mutagen/issues/548
        artist_names = music_df_row["Artist Name(s)"]
    else:
        artist_names = music_df_row["Artist Name(s)"].split(",")

    return {
        artist_tag: artist_names,
        title_tag: music_df_row["Track Name"],
    }


def set_file_metadata_tags(filepath: str, metadata_tags: dict):
    file_extension = os.path.splitext(filepath)[1]
    tag_handling_class = METADATA_CLASSES[file_extension]
    tag_dict = tag_handling_class(filepath)
    for key, value in metadata_tags.items():
        tag_dict[key] = value
    tag_dict.save()
