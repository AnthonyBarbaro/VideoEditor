import os
import subprocess
import whisper
import warnings
import openai
from random import randint

warnings.filterwarnings("ignore", category=FutureWarning)

# 1) Configure your OpenAI API key
openai.api_key = os.getenv("OPENAI_API_KEY")  # Set your OpenAI API key as an environment variable

def main():
    """
    Full pipeline with dynamic subtitle toggling, OpenAI clickbait title generation,
    and an overlay at the boundary between two stacked clips.
    """
    # === (A) Configuration ===
    ffmpeg_path = r"C:\Users\antho\miniconda3\envs\tiktok_env\Library\bin\ffmpeg.exe"

    # Input videos
    main_video = "videos/main2.mp4"
    bottom_video = "videos/bottom1.mp4"

    # Intermediate / output file names
    subtitles_file = "temp/main_subtitles.srt"
    main_subtitled_video = "temp/main_subtitled.mp4"
    stacked_video = "temp/vertical_merged.mp4"
    final_video = "temp/final_with_title.mp4"
    chunk_folder = "output/chunks"

    # Toggle options
    include_subtitles = False
    do_chunk_splitting = True

    # === (B) Transcribe with Whisper ===
    print("=== STEP 1: Transcribing main video with Whisper ===")
    model = whisper.load_model("tiny")
    result = model.transcribe(main_video, verbose=True)

    # Convert Whisper segments → SRT format
    srt_lines = []
    raw_text = []

    for i, seg in enumerate(result["segments"], start=1):
        start_ts = seconds_to_srt_timestamp(seg["start"])
        end_ts = seconds_to_srt_timestamp(seg["end"])
        text = seg["text"].strip()
        raw_text.append(text)

        # Build SRT lines
        srt_lines.append(f"{i}\n{start_ts} --> {end_ts}\n{text}\n\n")

    # Write out SRT
    os.makedirs(os.path.dirname(subtitles_file), exist_ok=True)
    with open(subtitles_file, "w", encoding="utf-8") as f:
        f.writelines(srt_lines)
    print(f"Generated SRT file at: {os.path.abspath(subtitles_file)}")

    # === (C) Use OpenAI to generate a clickbait title ===
    print("\n=== STEP 2: Generating AI clickbait title ===")
    combined_text = " ".join(raw_text)

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "user", "content": f"Generate a short, eye-catching clickbait title: {combined_text}"}
            ],
            max_tokens=50,
            temperature=1.0
        )
        ai_title = response["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"OpenAI API Error: {e}")
        ai_title = "You Won't Believe This Shocking Moment!"

    print(f"AI-Generated Title: {ai_title}")

    # === (D) (Optional) Burn subtitles ===
    if include_subtitles:
        print("\n=== STEP 3: Burning subtitles with FFmpeg ===")
        os.makedirs(os.path.dirname(main_subtitled_video), exist_ok=True)

        cmd_burn = [
            ffmpeg_path,
            "-y",
            "-i", main_video,
            "-vf", (
                f"subtitles={subtitles_file}:force_style='FontName=Arial,"
                "FontSize=30,"
                "PrimaryColour=&H00FFFF00,"
                "Alignment=2'"
            ),
            "-c:v", "libx264",
            "-c:a", "aac",
            main_subtitled_video
        ]
        subprocess.run(cmd_burn, check=True)
    else:
        print("Skipping subtitle burning...")
        main_subtitled_video = main_video

    # === (E) Stack main_subtitled + bottom video vertically ===
    print("\n=== STEP 4: Stacking videos vertically ===")
    cmd_stack = [
        ffmpeg_path,
        "-y",
        "-i", main_subtitled_video,
        "-i", bottom_video,
        "-filter_complex",
        (
            "[0:v]scale=1920:-1[v0];"
            "[1:v]scale=1920:-1[v1];"
            "[v0][v1]vstack=inputs=2"
        ),
        "-c:v", "libx264",
        "-crf", "23",
        "-preset", "fast",
        "-c:a", "aac",
        stacked_video
    ]
    subprocess.run(cmd_stack, check=True)

    # === (F) Overlay the AI-generated title ===
    print("\n=== STEP 5: Overlaying clickbait title on stacked video ===")
    escaped_title = ai_title.replace("'", "\\'").replace('"', '\\"')  # Escape single and double quotes for FFmpeg

    try:
        cmd_title_overlay = [
            ffmpeg_path,
            "-y",
            "-i", stacked_video,
            "-vf",
            (
                f"drawtext=fontfile='C\\\\:/Windows/Fonts/Arial.ttf':"
                f"text='{escaped_title}':"
                "x=(w-tw)/2:"
                "y=1080-(th/2):"
                "fontsize=64:"
                "fontcolor=white:"
                "box=1:"
                "boxcolor=black@0.5:"
                "boxborderw=20:"
                "enable='between(t,0,3)'"
            ),
            "-c:v", "libx264",
            "-c:a", "aac",
            final_video
        ]
        subprocess.run(cmd_title_overlay, check=True)
        print(f"Final video with overlay saved to: {os.path.abspath(final_video)}")
    except subprocess.CalledProcessError as e:
        print(f"Error: Failed to overlay title on video. Skipping overlay step.\nDetails: {e}")
        # Fall back to using the stacked video as the final video
        final_video = stacked_video

    # === (G) Split into 60-second chunks ===
    if do_chunk_splitting:
        print("\n=== STEP 6: Splitting final video into 60s chunks ===")
        os.makedirs(chunk_folder, exist_ok=True)
        chunk_pattern = os.path.join(chunk_folder, "chunk_%03d.mp4")

        cmd_split = [
            ffmpeg_path,
            "-y",
            "-i", final_video,
            "-c", "copy",
            "-map", "0",
            "-f", "segment",
            "-segment_time", "60",
            "-reset_timestamps", "1",
            chunk_pattern
        ]
        subprocess.run(cmd_split, check=True)
        print(f"Video split into chunks in: {os.path.abspath(chunk_folder)}")
    else:
        print("Skipping chunk splitting...")

    print("\n=== ALL DONE! ===")


def seconds_to_srt_timestamp(seconds: float) -> str:
    """Convert float seconds to SRT timestamp format: HH:MM:SS,mmm."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


if __name__ == "__main__":
    main()
