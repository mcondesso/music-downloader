import os

from pytube import YouTube

from src.file_metadata import FILE_EXTENSION_MP4, FILE_EXTENSION_MP3
from moviepy.video.io.VideoFileClip import VideoFileClip

NUM_RETRIES = 5

def get_audio_from_youtube(youtube_url: str, output_dir: str, filename: str) -> str:
    # Ensure the filename contains the correct extension
    if not filename.endswith(FILE_EXTENSION_MP4):
        filename += FILE_EXTENSION_MP4

    # Download audio track from provided youtube_url into a .mp4 file
    print(f"\nDownloading '{filename.rstrip(FILE_EXTENSION_MP4)}'")
    yt = YouTube(youtube_url)

    # Get stream with only audio in mp4 format, order by Average Bit Rate and take highest bit rate
    video = yt.streams.filter(subtype="mp4").order_by("abr").last()
    video.download(output_path=output_dir, max_retries=NUM_RETRIES, filename=filename)
    filepath = os.path.join(output_dir, filename)
    
    # Extract the audio file from the previously downloaded .mp4 file. 
    # In case of error, extracts the audio directly using the only_audio=True flag. This is not 
    # the default approach because this can lead to corrupted downloaded files, thus, it is only used
    # as a fallback.
    try:
        _extract_audio_mp4(filepath, filepath.replace(FILE_EXTENSION_MP4, FILE_EXTENSION_MP3))
        filepath = filepath.replace(FILE_EXTENSION_MP4, FILE_EXTENSION_MP3)
    except Exception as e:
        print(f"Error processing {filename}: {e}")
        os.remove(filepath)
        video = yt.streams.filter(only_audio=True, subtype="mp4").order_by("abr").last()
        video.download(output_path=output_dir, max_retries=NUM_RETRIES, filename=filename)
      
    return filepath  

# Extracts audio from .mp4 file and removes it once it is successfulle completed.
def _extract_audio_mp4(input_file, output_file):
    video_clip = VideoFileClip(input_file)
    audio_clip = video_clip.audio
    audio_clip.write_audiofile(output_file, codec='mp3')
    video_clip.close()
    os.remove(input_file)