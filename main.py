import os
import subprocess
import whisper
import warnings

warnings.filterwarnings("ignore", category=FutureWarning)

def main():
    """
    Full pipeline:
      1) Transcribe main video -> subtitles.srt
      2) Burn subtitles onto main video -> main_subtitled.mp4
      3) Stack subtitled main over bottom video -> vertical_merged_1080x1920.mp4
      4) Split final stacked video -> chunk_XXX.mp4
    """

    # 1) Point this to your ffmpeg.exe
    ffmpeg_path = r"C:\Users\antho\miniconda3\envs\tiktok_env\Library\bin\ffmpeg.exe"

    # 2) Paths for input videos
    main_video_path = "./videos/main1.mp4"
    bottom_video_path = "./videos/bottom1.mp4"

    # 3) Output folder structure
    temp_folder = "./temp"     # For temporary files (SRT + subtitled main)
    output_folder = "./output" # For final stacked + chunks
    os.makedirs(temp_folder, exist_ok=True)
    os.makedirs(output_folder, exist_ok=True)

    # 4) Filenames
    srt_path = os.path.join(temp_folder, "subtitles.srt")
    main_subtitled_path = os.path.join(temp_folder, "main_subtitled.mp4")
    stacked_vertical_path = os.path.join(output_folder, "vertical_merged_1080x1920.mp4")
    chunks_folder = os.path.join(output_folder, "chunks")

    # Step 1: Generate SRT subtitles via Whisper
    print("=== STEP 1: Transcribe main video with Whisper ===")
    generate_srt_with_whisper(
        input_video_path=main_video_path,
        output_srt_path=srt_path,
        model_size="tiny"   # 'tiny' is faster; 'medium'/'large' more accurate
    )

    # Step 2: Burn subtitles into the main video
    print("\n=== STEP 2: Burn subtitles onto main video ===")
    burn_subtitles_ffmpeg(
        ffmpeg_path=ffmpeg_path,
        video_in=main_video_path,
        srt_path=srt_path,
        video_out=main_subtitled_path
    )

    # Step 3: Stack the subtitled main over the bottom video in 1080x1920 format
    print("\n=== STEP 3: Stack main_subtitled + bottom video (1080x1920) ===")
    stack_videos_vertical(
        ffmpeg_path=ffmpeg_path,
        top_video=main_subtitled_path,
        bottom_video=bottom_video_path,
        output_path=stacked_vertical_path
    )

    # Step 4: Split the final stacked video into ~3-minute chunks
    print("\n=== STEP 4: Split final video into 3-minute chunks ===")
    split_video_into_chunks(
        ffmpeg_path=ffmpeg_path,
        input_video_path=stacked_vertical_path,
        chunk_length_seconds=180,
        output_dir=chunks_folder
    )

    print("\nAll done! Check the output folder for results.\n")


def generate_srt_with_whisper(input_video_path, output_srt_path, model_size="medium"):
    """
    Transcribe the audio in a video with Whisper and write an SRT file.
    """
    if not os.path.exists(input_video_path):
        raise FileNotFoundError(f"Video not found: {input_video_path}")

    print(f"Loading Whisper model: {model_size}")
    model = whisper.load_model(model_size)

    print(f"Transcribing audio in '{input_video_path}'...")
    result = model.transcribe(input_video_path)

    # Convert Whisper segments to SRT format
    srt_lines = []
    for i, seg in enumerate(result["segments"], start=1):
        start_ts = seconds_to_srt_timestamp(seg["start"])
        end_ts = seconds_to_srt_timestamp(seg["end"])
        text = seg["text"].strip()
        srt_lines.append(f"{i}\n{start_ts} --> {end_ts}\n{text}\n\n")

    with open(output_srt_path, "w", encoding="utf-8") as f:
        f.writelines(srt_lines)

    print(f"Generated SRT file at: {os.path.abspath(output_srt_path)}")


def burn_subtitles_ffmpeg(ffmpeg_path, video_in, srt_path, video_out):
    """
    Burn SRT subtitles into a video using FFmpeg, specifying full ffmpeg_path on Windows.
    """
    if not os.path.exists(video_in):
        raise FileNotFoundError(f"Video not found: {video_in}")
    if not os.path.exists(srt_path):
        raise FileNotFoundError(f"Subtitle file not found: {srt_path}")

    print(f"Burning subtitles from '{srt_path}' into '{video_in}'...")

    # Convert to absolute, forward-slashed paths
    video_in_abs = os.path.abspath(video_in).replace("\\", "/")
    srt_abs = os.path.abspath(srt_path).replace("\\", "/")
    video_out_abs = os.path.abspath(video_out).replace("\\", "/")

    # IMPORTANT: Use quotes around srt_abs inside the filter
    # so FFmpeg reads it as a single file path (even if it has spaces or colons)
    vf_filter = f'subtitles="{srt_abs}"'

    cmd = [
        ffmpeg_path,
        "-y",
        "-i", video_in_abs,
        "-vf", vf_filter,
        "-c:v", "libx264",
        "-c:a", "aac",
        video_out_abs
    ]
    print("FFmpeg command:\n", " ".join(cmd))
    subprocess.run(cmd, check=True)

    print(f"Created subtitled video: {os.path.abspath(video_out_abs)}")

def stack_videos_vertical(ffmpeg_path, top_video, bottom_video, output_path):
    """
    Stack top_video above bottom_video at 1080x1920.
    """
    if not os.path.exists(top_video):
        raise FileNotFoundError(f"Top video not found: {top_video}")
    if not os.path.exists(bottom_video):
        raise FileNotFoundError(f"Bottom video not found: {bottom_video}")

    print(f"Stacking '{top_video}' over '{bottom_video}' in 1080x1920 format...")
    cmd = [
        ffmpeg_path,
        "-y",
        "-i", top_video,
        "-i", bottom_video,
        "-filter_complex", "[0:v][1:v]vstack=inputs=2,scale=1080:1920",
        "-c:v", "libx264",
        "-crf", "23",
        "-preset", "fast",
        "-c:a", "aac",
        output_path
    ]
    print("FFmpeg command:\n", " ".join(cmd))
    subprocess.run(cmd, check=True)

    print(f"Created stacked video at: {os.path.abspath(output_path)}")


def split_video_into_chunks(ffmpeg_path, input_video_path, chunk_length_seconds, output_dir):
    """
    Split a video into N-second chunks using FFmpeg.
    """
    if not os.path.exists(input_video_path):
        raise FileNotFoundError(f"Input video not found: {input_video_path}")

    os.makedirs(output_dir, exist_ok=True)
    chunk_pattern = os.path.join(output_dir, "chunk_%03d.mp4")

    print(f"Splitting '{input_video_path}' into chunks of {chunk_length_seconds} seconds...")
    cmd = [
        ffmpeg_path,
        "-y",
        "-i", input_video_path,
        "-c", "copy",
        "-map", "0",
        "-f", "segment",
        "-segment_time", str(chunk_length_seconds),
        "-reset_timestamps", "1",
        chunk_pattern
    ]
    print("FFmpeg command:\n", " ".join(cmd))
    subprocess.run(cmd, check=True)

    print(f"Chunked files saved to: {os.path.abspath(output_dir)}")


def seconds_to_srt_timestamp(seconds):
    """
    Convert float seconds to an SRT timestamp: HH:MM:SS,mmm
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


if __name__ == "__main__":
    main()
