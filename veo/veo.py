import time
from google import genai

client = genai.Client(api_key="AIzaSyBj-XGMHpmeOMaNS7IOhOhmds-aYOfuC0U")

prompt = "A serene landscape with rolling green hills, a river flowing, and birds flying in the sky"

# Step 1: Generate video with Veo 3 directly from prompt.
operation = client.models.generate_videos(
    model="veo-3.0-generate-001",
    prompt=prompt,
    config={
        "aspect_ratio": "16:9",
        "resolution": "1080p"
        # ⚠️ don't include generate_audio — not supported in current SDK
    }
)

# Step 2: Poll until the video is ready.
while not operation.done:
    print("Waiting for Veo 3 video generation to complete...")
    time.sleep(10)
    operation = client.operations.get(operation)

# Step 3: Download the video.
video = operation.response.generated_videos[0]
client.files.download(file=video.video)
video.video.save("veo3_output.mp4")

print("✅ Generated video saved to veo3_output.mp4")
