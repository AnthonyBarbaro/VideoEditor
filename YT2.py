import yt_dlp
import os

def download_youtube_video(video_url):
    """
    Downloads a YouTube video using yt-dlp and saves it to the 'videos/' directory.
    """
    # Set the fixed download path to the 'videos/' directory
    save_path = os.path.join(os.getcwd(), 'videos')

    # Ensure the directory exists
    os.makedirs(save_path, exist_ok=True)

    # Specify output template and options
    ydl_opts = {
        'outtmpl': os.path.join(save_path, '%(title)s.%(ext)s'),  # Save file in specified directory
        'format': 'bestvideo+bestaudio/best',  # Download best video and audio
        'merge_output_format': 'mp4',  # Ensure the final output is MP4
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)  # Extract info and download
            file_path = os.path.join(save_path, f"{info['title']}.mp4")
        print(f"Video downloaded successfully to: {file_path}")
    except Exception as e:
        print(f"An error occurred: {e}")

# Example usage
if __name__ == "__main__":
    video_url = input("Enter the YouTube video URL: ").strip()
    download_youtube_video(video_url)
