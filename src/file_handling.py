"""
File handling utilities for music-downloader project.
"""

import os


def scan_directory_for_audio_files(directory, audio_extensions):
    """
    Recursively scan a directory for audio files with given extensions.
    Returns generator of file paths.
    """
    for root, _, files in os.walk(directory):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in audio_extensions:
                yield os.path.join(root, file)
