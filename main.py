import os
import subprocess
import whisper
import warnings

warnings.filterwarnings("ignore", category=FutureWarning)

def seconds_to_srt_timestamp(seconds):
    """Convert float seconds to SRT timestamp format: HH:MM:SS,mmm."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


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
    main_video = "videos/main1.mp4"  # The main “top” video
    bottom_video = "videos/bottom.mp4"  # The bottom video

    # 3) Output file names/directories
    subtitles_file = "temp/main_subtitles.srt"
    main_subtitled_video = "temp/main_subtitled.mp4"
    stacked_video = "temp/vertical_merged.mp4"
    chunk_folder = "output/chunks"  # Where we'll store chunks if we split

    # Ensure directories exist
    os.makedirs("temp", exist_ok=True)
    os.makedirs(chunk_folder, exist_ok=True)

    try:
        # === STEP A: Transcribe with Whisper ===
        print("=== STEP A: Transcribing with Whisper ===")
        model = whisper.load_model("tiny")  # "tiny" is fastest; "medium"/"large" more accurate
        result = model.transcribe(main_video, verbose=True)  # verbose=True to see progress

        # Convert Whisper segments → SRT format
        srt_lines = []
        for i, seg in enumerate(result["segments"], start=1):
            start_time = seg["start"]
            end_time = seg["end"]
            full_text = seg["text"].strip()

            # Split subtitles into smaller chunks
            words = full_text.split()
            chunk_size = 3  # Number of words per chunk
            chunks = [words[i:i + chunk_size] for i in range(0, len(words), chunk_size)]

            # Adjust timing per chunk
            chunk_duration = (end_time - start_time) / len(chunks)

            for j, chunk in enumerate(chunks):
                chunk_start = start_time + j * chunk_duration
                chunk_end = chunk_start + chunk_duration

                # Generate timestamp and subtitle text
                start_ts = seconds_to_srt_timestamp(chunk_start)
                end_ts = seconds_to_srt_timestamp(chunk_end)
                text = " ".join(chunk)

                # Append to SRT lines
                srt_lines.append(f"{i}-{j}\n{start_ts} --> {end_ts}\n{text}\n\n")

        with open(subtitles_file, "w", encoding="utf-8") as f:
            f.writelines(srt_lines)

        print(f"Generated SRT file at: {os.path.abspath(subtitles_file)}")
    except Exception as e:
        print(f"Error during transcription: {e}")
        return

    try:
        # === STEP B: Burn subtitles into the main video ===
        print("\n=== STEP B: Burning subtitles with FFmpeg ===")
        cmd_burn = [
            ffmpeg_path,
            "-y",                      # Overwrite output
            "-i", main_video,          # Input file
            "-vf", f"subtitles={subtitles_file}:force_style='FontSize=24'",  # Set subtitle font size
            "-c:v", "libx264",         # Encode video with x264
            "-c:a", "aac",             # Encode audio with AAC
            main_subtitled_video
        ]
        print("Running command:")
        print(" ".join(cmd_burn))
        subprocess.run(cmd_burn, check=True)
        print(f"Created video with burned subtitles: {os.path.abspath(main_subtitled_video)}")
    except Exception as e:
        print(f"Error during subtitle burning: {e}")
        return

    try:
        # === STEP C: Stack main_subtitled + bottom video vertically ===
        print("\n=== STEP C: Stacking Videos Vertically ===")
        cmd_stack = [
            ffmpeg_path,
            "-y",
            "-i", main_subtitled_video,
            "-i", bottom_video,
            "-filter_complex",
            "[0:v]scale=1920:-1[v0];[1:v]scale=1920:-1[v1];[v0][v1]vstack=inputs=2",
            "-c:v", "libx264",
            "-crf", "23",
            "-preset", "fast",
            "-c:a", "aac",
            stacked_video
        ]
        print("Running command:")
        print(" ".join(cmd_stack))
        subprocess.run(cmd_stack, check=True)
        print(f"Created stacked video: {os.path.abspath(stacked_video)}")
    except Exception as e:
        print(f"Error during video stacking: {e}")
        return

    try:
        # === STEP D: (Optional) Split the stacked video into chunks ===
        print("\n=== STEP D: Splitting into 60-second chunks ===")
        chunk_pattern = os.path.join(chunk_folder, "chunk_%03d.mp4")

        cmd_split = [
            ffmpeg_path,
            "-y",
            "-i", stacked_video,
            "-c", "copy",
            "-map", "0",
            "-f", "segment",
            "-segment_time", "60",  # 60 seconds per chunk
            "-reset_timestamps", "1",
            chunk_pattern
        ]
        print("Running command:")
        print(" ".join(cmd_split))
        subprocess.run(cmd_split, check=True)
        print(f"Video split into chunks in: {os.path.abspath(chunk_folder)}")
    except Exception as e:
        print(f"Error during video splitting: {e}")
        return

    print("\n=== ALL DONE! Check for results in the current folder. ===")


if __name__ == "__main__":
    main()
