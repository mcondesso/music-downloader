import os

from moviepy.video.io.VideoFileClip import VideoFileClip
from pytube import YouTube

from src.file_metadata import FILE_EXTENSION_MP3, FILE_EXTENSION_MP4

NUM_RETRIES = 5


def get_audio_from_youtube(youtube_url: str, output_dir: str, filename: str) -> str:
    video_filepath = _download_mp4_video_from_youtube(youtube_url, output_dir, filename)

    video_processing_failed = False
    try:
        # Extract the audio file from the previously downloaded .mp4 file.
        audio_filepath = _extract_mp3_audio_from_mp4_video(video_filepath)
    except Exception as error:
        print(f"Error extracting mp3 from {video_filepath}: {error}")
        video_processing_failed = True
    finally:
        if os.path.exists(video_filepath):
            os.remove(video_filepath)

    # In case of error, download the audio directly using the only_audio=True flag. This is not
    # the default approach because this can lead to corrupted downloaded files, so we only use
    # it as a fallback.
    if video_processing_failed:
        audio_filepath = _download_mp4_audio_from_youtube(
            youtube_url, output_dir, filename
        )

    return audio_filepath


def _download_mp4_video_from_youtube(
    youtube_url: str, output_dir: str, filename: str
) -> str:
    # Ensure the filename contains the correct extension
    if not filename.endswith(FILE_EXTENSION_MP4):
        filename += FILE_EXTENSION_MP4

    print(f"\nDownloading '{filename.rstrip(FILE_EXTENSION_MP4)}'")

    yt = YouTube(youtube_url)

    # Get stream with video in mp4 format, order by Average Bit Rate and take highest bit rate
    video = yt.streams.filter(subtype="mp4").order_by("abr").last()
    video.download(output_path=output_dir, max_retries=NUM_RETRIES, filename=filename)

    return os.path.join(output_dir, filename)


def _download_mp4_audio_from_youtube(
    youtube_url: str, output_dir: str, filename: str
) -> str:
    # Ensure the filename contains the correct extension
    if not filename.endswith(FILE_EXTENSION_MP4):
        filename += FILE_EXTENSION_MP4

    print(f"\nDownloading '{filename.rstrip(FILE_EXTENSION_MP4)}'")

    yt = YouTube(youtube_url)

    # Get stream with only audio in mp4 format, order by Average Bit Rate and take highest bit rate
    video = yt.streams.filter(only_audio=True, subtype="mp4").order_by("abr").last()

    video.download(output_path=output_dir, max_retries=NUM_RETRIES, filename=filename)

    return os.path.join(output_dir, filename)


def _extract_mp3_audio_from_mp4_video(video_filepath: str) -> str:
    if not video_filepath.endswith(FILE_EXTENSION_MP4):
        raise ValueError(f"Input video is not in mp4 format: {video_filepath}")

    output_filename = video_filepath.replace(FILE_EXTENSION_MP4, FILE_EXTENSION_MP3)

    video_clip = VideoFileClip(video_filepath)
    audio_clip = video_clip.audio
    audio_clip.write_audiofile(output_filename, codec="mp3")
    video_clip.close()

    return output_filename
