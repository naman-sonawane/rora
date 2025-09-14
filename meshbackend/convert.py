import cv2
import os

def video_to_frames(video_path, output_folder, fps=13):
    # Create output folder if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)

    # Open video
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("Error: Cannot open video.")
        return

    # Get original FPS
    original_fps = cap.get(cv2.CAP_PROP_FPS)
    frame_interval = int(round(original_fps / fps))  # pick frames to match desired fps

    frame_count = 0
    saved_count = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Save frame every interval
        if frame_count % frame_interval == 0:
            frame_name = os.path.join(output_folder, f"frame_{saved_count:04d}.jpg")
            cv2.imwrite(frame_name, frame)
            saved_count += 1

        frame_count += 1

    cap.release()
    print(f"Done. Extracted {saved_count} frames at {fps} FPS.")

# Example usage:
video_to_frames("IMG_2613.mov", "output_frames", fps=14)