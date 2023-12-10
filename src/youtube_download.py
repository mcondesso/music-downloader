from pytube import YouTube

NUM_RETRIES = 5


def download_mp4(youtube_url: str, output_dir: str, filename: str):
    # Ensure the filename contains the correct extension
    if not filename.endswith(".mp4"):
        filename += ".mp4"

    # Download audio track from provided youtube_url into a .mp4 file
    print(f"\nDownloading '{filename.rstrip('.mp4')}'")

    yt = YouTube(youtube_url)

    # Get stream with only audio, order by Average Bit Rate and take highest
    video = yt.streams.filter(only_audio=True, subtype="mp4").order_by("abr").last()

    video.download(output_path=output_dir, max_retries=NUM_RETRIES, filename=filename)
