import os
import subprocess
import whisper
import warnings

warnings.filterwarnings("ignore", category=FutureWarning)

def main():
    """
    Full pipeline:
      1) Transcribe main video -> main_subtitles.srt
      2) Burn subtitles -> main_subtitled.mp4
      3) Stack main_subtitled + bottom video -> vertical_merged.mp4
      4) (Optional) Split final video into chunks -> chunk_XXX.mp4
    """

    # 1) Point this to your ffmpeg.exe
    ffmpeg_path = r"C:\Users\antho\miniconda3\envs\tiktok_env\Library\bin\ffmpeg.exe"

    # 2) Paths for input videos
    main_video = "videos/main1.mp4"        # The main “top” video
    bottom_video = "videos/bottom1.mp4"    # The bottom video

    # 3) Output file names/directories
    subtitles_file = "main_subtitles.srt"
    main_subtitled_video = "main_subtitled.mp4"
    stacked_video = "vertical_merged.mp4"
    chunk_folder = "chunks"  # Where we'll store chunks if we split

    # === STEP A: Transcribe with Whisper ===
    print("=== STEP A: Transcribing with Whisper ===")
    model = whisper.load_model("tiny")  # "tiny" is fastest; "medium"/"large" more accurate
    result = model.transcribe(main_video, verbose=True)  # verbose=True to see progress

    # Convert Whisper segments → SRT format
    srt_lines = []
    for i, seg in enumerate(result["segments"], start=1):
        start_ts = seconds_to_srt_timestamp(seg["start"])
        end_ts = seconds_to_srt_timestamp(seg["end"])
        text = seg["text"].strip()
        srt_lines.append(f"{i}\n{start_ts} --> {end_ts}\n{text}\n\n")

    with open(subtitles_file, "w", encoding="utf-8") as f:
        f.writelines(srt_lines)

    print(f"Generated SRT file at: {os.path.abspath(subtitles_file)}")

    # === STEP B: Burn subtitles into the main video ===
    print("\n=== STEP B: Burning subtitles with FFmpeg ===")
    cmd_burn = [
        ffmpeg_path,
        "-y",                      # Overwrite output
        "-i", main_video,          # Input file
        "-vf", f"subtitles={subtitles_file}",  # Add SRT subtitles
        "-c:v", "libx264",         # Encode video with x264
        "-c:a", "aac",             # Encode audio with AAC
        main_subtitled_video
    ]
    print("Running command:")
    print(" ".join(cmd_burn))
    subprocess.run(cmd_burn, check=True)
    print(f"Created video with burned subtitles: {os.path.abspath(main_subtitled_video)}")

    # === STEP C: Stack main_subtitled + bottom video vertically ===
    print("\n=== STEP C: Stacking Videos Vertically ===")
    cmd_stack = [
        ffmpeg_path,
        "-y",
        "-i", main_subtitled_video,  # top video
        "-i", bottom_video,          # bottom video
        # vstack merges them top/bottom; scale=1080:1920 if you want a TikTok-style vertical
        "-filter_complex", "[0:v][1:v]vstack=inputs=2,scale=1080:1920",
        "-c:v", "libx264",
        "-crf", "23",       # Adjust CRF for desired quality (lower=better)
        "-preset", "fast",  # or "medium"/"slow" for better compression
        "-c:a", "aac",
        stacked_video
    ]
    print("Running command:")
    print(" ".join(cmd_stack))
    subprocess.run(cmd_stack, check=True)
    print(f"Created stacked video: {os.path.abspath(stacked_video)}")

    # === STEP D: (Optional) Split the stacked video into chunks ===
    print("\n=== STEP D: Splitting into 180-second chunks ===")
    os.makedirs(chunk_folder, exist_ok=True)
    chunk_pattern = os.path.join(chunk_folder, "chunk_%03d.mp4")

    cmd_split = [
        ffmpeg_path,
        "-y",
        "-i", stacked_video,
        "-c", "copy",
        "-map", "0",
        "-f", "segment",
        "-segment_time", "180",  # 3 minutes
        "-reset_timestamps", "1",
        chunk_pattern
    ]
    print("Running command:")
    print(" ".join(cmd_split))
    subprocess.run(cmd_split, check=True)
    print(f"Video split into chunks in: {os.path.abspath(chunk_folder)}")

    print("\n=== ALL DONE! Check for results in the current folder. ===")


def seconds_to_srt_timestamp(seconds):
    """Convert float seconds to SRT timestamp format: HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


if __name__ == "__main__":
    main()
