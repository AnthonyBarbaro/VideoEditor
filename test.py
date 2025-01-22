import os
import subprocess
import warnings
import openai
import torch
import whisper
from random import randint

warnings.filterwarnings("ignore", category=FutureWarning)

# 1) Configure your OpenAI API key
openai.api_key = os.getenv("OPENAI_API_KEY")  # Set your OpenAI API key as an environment variable

def main():
    """
    Full pipeline with GPU-based Whisper transcription, dynamic 4-word chunk subtitles,
    OpenAI clickbait title generation, and GPU-accelerated FFmpeg with NVENC.
    """

    # === (A) Configuration ===
    # If you're on Windows, adjust the ffmpeg path if needed
    ffmpeg_path = "ffmpeg"  # or a full path on Windows, e.g. r"C:\Path\to\ffmpeg.exe"

    # Input videos
    main_video = "videos/main4.mp4"
    bottom_video = "videos/bottom2.mp4"

    # Intermediate / output file names
    subtitles_file = "temp/main_subtitles.srt"
    main_subtitled_video = "temp/main_subtitled.mp4"
    stacked_video = "temp/vertical_merged.mp4"
    final_video = "temp/final_with_title.mp4"
    chunk_folder = "output/chunks"

    # Toggle options
    include_subtitles = True       # If True, burn subtitles
    do_chunk_splitting = True      # If True, split final video into 60s chunks
    do_clickbait_title = True      # If True, use OpenAI GPT to generate a title

    os.makedirs("temp", exist_ok=True)
    os.makedirs("output", exist_ok=True)

    # === (B) GPU-based Whisper Transcription ===
    print("=== STEP 1: Transcribing main video with Whisper (GPU) ===")

    # Check if CUDA is available
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}")

    # Load Whisper model onto GPU if available
    model = whisper.load_model("tiny", device=device)

    # Transcribe with Whisper, using FP16 if on CUDA
    fp16 = (device == "cuda")
    result = model.transcribe(main_video, verbose=True, fp16=fp16)

    # Convert segments → SRT format with 4-word chunking
    srt_lines = []
    raw_text = []
    segment_counter = 1

    for seg in result["segments"]:
        start_time = seg["start"]
        end_time = seg["end"]
        full_text = seg["text"].strip()

        # Split into 4-word chunks
        words = full_text.split()
        chunk_size = 4

        # Number of sub-chunks for this segment
        num_chunks = (len(words) + chunk_size - 1) // chunk_size

        # Duration per chunk
        segment_duration = end_time - start_time
        sub_chunk_duration = segment_duration / max(num_chunks, 1)

        for i in range(num_chunks):
            chunk_start = start_time + i * sub_chunk_duration
            chunk_end = start_time + (i + 1) * sub_chunk_duration

            chunk_words = words[i * chunk_size:(i + 1) * chunk_size]
            chunk_text = " ".join(chunk_words)

            raw_text.append(chunk_text)

            start_ts = seconds_to_srt_timestamp(chunk_start)
            end_ts = seconds_to_srt_timestamp(chunk_end)

            srt_lines.append(f"{segment_counter}\n{start_ts} --> {end_ts}\n{chunk_text}\n\n")
            segment_counter += 1

    # Write out SRT
    with open(subtitles_file, "w", encoding="utf-8") as f:
        f.writelines(srt_lines)

    print(f"Generated 4-word-chunk SRT at: {os.path.abspath(subtitles_file)}")

    # === (C) OpenAI GPT for Clickbait Title ===
    ai_title = "DEFAULT CLICKBAIT TITLE"
    if do_clickbait_title:
        print("\n=== STEP 2: Generating AI clickbait title ===")
        combined_text = " ".join(raw_text)
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": f"Generate a short, eye-catching clickbait title from: {combined_text}"}],
                max_tokens=50,
                temperature=1.0
            )
            ai_title = response["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"OpenAI API Error: {e}")
            ai_title = "You Won't Believe This Shocking Moment!"

        print(f"AI-Generated Title: {ai_title}")
    else:
        print("Skipping AI title generation...")

    # === (D) (Optional) Burn subtitles with GPU-friendly FFmpeg command ===
    if include_subtitles:
        print("\n=== STEP 3: Burning subtitles with GPU (NVENC) ===")
        cmd_burn = [
            ffmpeg_path,
            "-y",
            "-hwaccel", "cuda",             # Use GPU for decoding if possible
            "-i", main_video,
            "-vf", f"subtitles={subtitles_file}:force_style='FontName=Arial,FontSize=20'",
            "-c:v", "h264_nvenc",           # GPU-based NVENC encoding
            "-b:v", "5M",
            "-preset", "fast",
            "-c:a", "aac",
            main_subtitled_video
        ]
        print("Running burn command:", " ".join(cmd_burn))
        subprocess.run(cmd_burn, check=True)
    else:
        print("Skipping subtitle burning...")
        main_subtitled_video = main_video

    # === (E) Stack main_subtitled + bottom video vertically with NVENC ===
    print("\n=== STEP 4: Stacking videos vertically (GPU) ===")
    cmd_stack = [
        ffmpeg_path,
        "-y",
        "-hwaccel", "cuda",
        "-i", main_subtitled_video,
        "-i", bottom_video,
        "-filter_complex",
        (
            "[0:v]scale=1920:-1:force_original_aspect_ratio=decrease[v0];"
            "[1:v]scale=1920:-1:force_original_aspect_ratio=decrease[v1];"
            "[v0][v1]vstack=inputs=2"
        ),
        "-c:v", "h264_nvenc",
        "-b:v", "5M",
        "-preset", "fast",
        "-c:a", "aac",
        stacked_video
    ]
    print("Running stack command:", " ".join(cmd_stack))
    subprocess.run(cmd_stack, check=True)

    # === (F) Overlay the AI-generated title with GPU support ===
    print("\n=== STEP 5: Overlaying clickbait title on stacked video (GPU) ===")
    escaped_title = ai_title.replace("'", "\\'").replace('"', '\\"')
    try:
        cmd_title_overlay = [
            ffmpeg_path,
            "-y",
            "-hwaccel", "cuda",
            "-i", stacked_video,
            "-vf",
            (
                f"drawtext=fontfile='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf':"
                f"text='{escaped_title}':"
                "x=(w-tw)/2:"
                "y=50:"                # Title near the top
                "fontsize=64:"
                "fontcolor=white:"
                "box=1:"
                "boxcolor=black@0.5:"
                "boxborderw=20:"
                "enable='between(t,0,4)'"
            ),
            "-c:v", "h264_nvenc",
            "-b:v", "5M",
            "-preset", "fast",
            "-c:a", "aac",
            final_video
        ]
        print("Running title overlay command:", " ".join(cmd_title_overlay))
        subprocess.run(cmd_title_overlay, check=True)
        print(f"Final video with overlay saved to: {os.path.abspath(final_video)}")
    except subprocess.CalledProcessError as e:
        print(f"Error: Failed to overlay title on video. Details: {e}\nFalling back to stacked video as final.")
        final_video = stacked_video

    # === (G) Split into 60-second chunks ===
    if do_chunk_splitting:
        print("\n=== STEP 6: Splitting final video into 60s chunks (GPU decode if possible) ===")
        os.makedirs(chunk_folder, exist_ok=True)
        chunk_pattern = os.path.join(chunk_folder, "chunk_%03d.mp4")

        cmd_split = [
            ffmpeg_path,
            "-y",
            "-hwaccel", "cuda",
            "-i", final_video,
            "-c", "copy",           # copy to avoid re-encoding
            "-map", "0",
            "-f", "segment",
            "-segment_time", "60",
            "-reset_timestamps", "1",
            chunk_pattern
        ]
        print("Running split command:", " ".join(cmd_split))
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
