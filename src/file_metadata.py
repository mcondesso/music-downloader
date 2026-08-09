"""Module for handling file metadata for the supported file types."""

import os

from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3
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
FILE_EXTENSION_M4A = ".m4a"

SUPPORTED_FORMATS = {FILE_EXTENSION_MP3, FILE_EXTENSION_MP4, FILE_EXTENSION_M4A}

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

# .m4a files are MP4 containers, so they share the MP4 tag mapping and handler
METADATA_TAGS[FILE_EXTENSION_M4A] = METADATA_TAGS[FILE_EXTENSION_MP4]
METADATA_CLASSES[FILE_EXTENSION_M4A] = METADATA_CLASSES[FILE_EXTENSION_MP4]


def extract_metadata_from_file(filepath: str) -> dict:
    """Extract metadata from an audio file (artist, title, duration, genres, tempo)."""
    ext = os.path.splitext(filepath)[1].lower()
    metadata = {
        "artist": "",
        "title": "",
        "duration": 0,
        "genres": "",
        "tempo": "",
        "bit_rate": "",
    }
    try:
        if ext == FILE_EXTENSION_MP3:
            audio = EasyID3(filepath)
            metadata["artist"] = ",".join(audio.get("artist", [""]))
            metadata["title"] = ",".join(audio.get("title", [""]))
            metadata["genres"] = ",".join(audio.get("genre", [""]))
            metadata["tempo"] = ",".join(audio.get("bpm", [""]))

            audio_mp3 = MP3(filepath)
            metadata["duration"] = int(audio_mp3.info.length)
            # Bit rate in kbps
            if hasattr(audio_mp3.info, "bitrate"):
                metadata["bit_rate"] = str(int(audio_mp3.info.bitrate // 1000))
        elif ext in (FILE_EXTENSION_MP4, FILE_EXTENSION_M4A):
            audio = MP4(filepath)
            metadata["artist"] = audio.tags.get("©ART", [""])[0]
            metadata["title"] = audio.tags.get("©nam", [""])[0]
            metadata["genres"] = audio.tags.get("©gen", [""])[0]
            metadata["tempo"] = str(audio.tags.get("tmpo", [""])[0])
            metadata["duration"] = int(audio.info.length)
            # Bit rate not available for mp4
            metadata["bit_rate"] = ""
    except Exception as e:
        pass  # Could log error if needed
    return metadata



def prepare_metadata_tags(
    music_df_row: dict, file_extension: str, artist_in_title: bool = False
) -> dict:
    """This function prepares the available metadata tags to be written onto a
    music file, depending on the file format."""
    artist_tag = METADATA_TAGS[file_extension]["artist"]
    title_tag = METADATA_TAGS[file_extension]["title"]
    genre_tag = METADATA_TAGS[file_extension]["genre"]
    tempo_tag = METADATA_TAGS[file_extension]["tempo"]

    metadata_tags = {}

    if file_extension in (FILE_EXTENSION_MP4, FILE_EXTENSION_M4A):
        artist_names = music_df_row[COLUMN_ARTIST_NAME].replace(", ", "/")
    else:
        artist_names = music_df_row[COLUMN_ARTIST_NAME].split(",")
    
    if artist_names:
        metadata_tags[artist_tag] = artist_names

    # Determine the title based on artist_in_title flag
    if artist_in_title:
        title = get_song_search_string(music_df_row)
    else:
        title = music_df_row[COLUMN_TRACK_NAME]
    
    if title:
        metadata_tags[title_tag] = title

    if genre := music_df_row.get(COLUMN_GENRES):
        metadata_tags[genre_tag] = genre

    if bpm := music_df_row.get(COLUMN_TEMPO):
        metadata_tags[tempo_tag] = [round(float(bpm))]

    return metadata_tags


def set_file_metadata_tags(filepath: str, metadata_tags: dict):
    """This function sets the provided metadata tags onto a file."""
    file_extension = os.path.splitext(filepath)[1]
    tag_handling_class = METADATA_CLASSES[file_extension]
    tag_dict = tag_handling_class(filepath)
    for key, value in metadata_tags.items():
        tag_dict[key] = value
    tag_dict.save()
