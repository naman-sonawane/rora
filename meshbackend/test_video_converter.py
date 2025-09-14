from video_to_frames import VideoToFramesConverter
import os

def test_converter():
    """Test the video converter with a sample video"""
    
    # Initialize converter
    converter = VideoToFramesConverter(fps=10, output_format="jpg")
    
    # Check if FFmpeg is available
    if not converter.check_ffmpeg():
        print("\n❌ Please install FFmpeg first")
        return
    
    # Example usage - replace with your actual video file
    video_path = "IMG_2613.mov"  # Change this to your video file
    
    if not os.path.exists(video_path):
        print(f"❌ Video file not found: {video_path}")
        print("Please place a video file in the current directory or update the path")
        return
    
    print(f"🎬 Testing with video: {video_path}")
    
    # Option 1: Just extract frames
    print("\n📸 Option 1: Extract frames only")
    converter.extract_frames(video_path, "test_frames", "frame")
    
    # Option 2: Complete pipeline for COLMAP
    print("\n🔄 Option 2: Complete pipeline (Video → PPM)")
    converter.process_video_to_ppm(video_path, "basement_0001a", "r")
    
    print("\n✅ Test completed!")

if __name__ == "__main__":
    test_converter()

