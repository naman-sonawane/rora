import os
import time
import boto3
import google.generativeai as genai

# === CONFIG ===
WATCH_DIR = "/home/ubuntu/input_videos"
S3_BUCKET = "rorabucket"
PLACEHOLDER_PLY = "test.ply"
CHECK_INTERVAL = 5  # seconds

# Gemini API Key (must be set as env var before running)
GEMINI_API_KEY = "gemini_api_key"

# Init AWS + Gemini
s3 = boto3.client("s3")
genai.configure(api_key=GEMINI_API_KEY)

def process_video(video_path, base_name):
    """
    Process video with Gemini: generate narration text
    """
    try:
        # Upload file to Gemini
        myfile = genai.upload_file(video_path)
        print(f"[Lambda] Uploaded {video_path} to Gemini (id={myfile.name})")

        # Wait until Gemini marks the file ACTIVE
        while myfile.state.name != "ACTIVE":
            print(f"[Lambda] Waiting for Gemini file to be ACTIVE (current: {myfile.state.name})...")
            time.sleep(2)
            myfile = genai.get_file(myfile.name)

        # Request narration
        prompt = "You are a narrator describing what is happening in the video. Use language appropriate for how narrators tend to talk. Imagine yourself in the role of someone who is speaking for National Geographic. Keep your words concise (less than 100 characters)."
        response = genai.GenerativeModel("gemini-2.5-flash").generate_content([myfile, prompt])

        narration_text = response.text
        narration_file = f"{base_name}_narration.txt"

        # Write narration locally
        with open(narration_file, "w") as f:
            f.write(narration_text)

        # Upload narration to S3
        s3.upload_file(narration_file, S3_BUCKET, narration_file)
        print(f"[Lambda] Uploaded narration text → s3://{S3_BUCKET}/{narration_file}")

    except Exception as e:
        print(f"[Lambda] Gemini processing failed for {video_path}: {e}")


def main():
    seen = set()
    print(f"[Lambda] Watching {WATCH_DIR} for new videos...")

    while True:
        for fname in os.listdir(WATCH_DIR):
            if fname.lower().endswith((".mp4", ".mov")) and fname not in seen:
                seen.add(fname)
                video_path = os.path.join(WATCH_DIR, fname)
                base, _ = os.path.splitext(fname)

                print(f"[Lambda] Detected new input video: {fname}")
                print(f"[Lambda] Processing {fname}...")

                # === Upload placeholder PLY ===
                s3_key = f"{base}.ply"
                try:
                    s3.upload_file(PLACEHOLDER_PLY, S3_BUCKET, s3_key)
                    print(f"[Lambda] Uploaded {PLACEHOLDER_PLY} as {s3_key}")
                except Exception as e:
                    print(f"[Lambda] Failed to upload PLY: {e}")

                # === Gemini Narration ===
                process_video(video_path, base)

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
