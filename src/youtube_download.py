import os

from pytube import YouTube

from src.file_metadata import FILE_EXTENSION_MP4


NUM_RETRIES = 5

def get_audio_from_youtube(youtube_url: str, output_dir: str, filename: str) -> str:
    return _download_mp4_audio_from_youtube(youtube_url, output_dir, filename)


def _download_mp4_video_from_youtube(youtube_url: str, output_dir: str, filename: str) -> str:
    raise NotImplementedError("Implementa-me oh malandro")


def _download_mp4_audio_from_youtube(youtube_url: str, output_dir: str, filename: str) -> str:
    # Ensure the filename contains the correct extension
    if not filename.endswith(FILE_EXTENSION_MP4):
        filename += FILE_EXTENSION_MP4

    # Download audio track from provided youtube_url into a .mp4 file
    print(f"\nDownloading '{filename.rstrip(FILE_EXTENSION_MP4)}'")

    yt = YouTube(youtube_url)

    # Get stream with only audio in mp4 format, order by Average Bit Rate and take highest bit rate
    video = yt.streams.filter(only_audio=True, subtype="mp4").order_by("abr").last()

    video.download(output_path=output_dir, max_retries=NUM_RETRIES, filename=filename)

    return os.path.join(output_dir, filename)
