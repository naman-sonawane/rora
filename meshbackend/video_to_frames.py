from pathlib import Path
import subprocess
import os
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image

class VideoToFramesConverter:
    def __init__(self, fps=10, output_format="ppm"):
        self.fps = fps
        self.output_format = output_format.lower()
        self.supported_formats = ["ppm", "png", "jpg", "jpeg"]
        
        if self.output_format not in self.supported_formats:
            raise ValueError(f"Unsupported format: {output_format}. Supported: {self.supported_formats}")
    
    def check_ffmpeg(self):
        """Check if FFmpeg is installed and accessible"""
        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path:
            print(f"✅ FFmpeg found at: {ffmpeg_path}")
            return True
        else:
            print("❌ FFmpeg not found in PATH")
            print("\n🔧 To install FFmpeg:")
            print("1. Download from: https://ffmpeg.org/download.html")
            print("2. Or use conda: conda install -c conda-forge ffmpeg")
            print("3. Or use chocolatey: choco install ffmpeg")
            print("4. Add FFmpeg to your system PATH")
            return False
    
    def extract_frames(self, video_path, output_dir="extracted_frames", prefix="frame"):
        """
        Extract frames from video at specified FPS
        
        Args:
            video_path (str): Path to input video file
            output_dir (str): Directory to save extracted frames
            prefix (str): Prefix for output frame filenames
        """
        if not self.check_ffmpeg():
            return False
        
        video_path = Path(video_path)
        if not video_path.exists():
            print(f"❌ Video file not found: {video_path}")
            return False
        
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"🎬 Extracting frames from: {video_path}")
        print(f"📁 Output directory: {output_dir}")
        print(f"⚡ Frame rate: {self.fps} FPS")
        print(f"🖼️  Format: {self.output_format.upper()}")
        
        # FFmpeg command to extract frames
        output_pattern = output_dir / f"{prefix}_%06d.{self.output_format}"
        
        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-vf", f"fps={self.fps}",
            "-q:v", "2",  # High quality
            "-y",  # Overwrite output files
            str(output_pattern)
        ]
        
        try:
            print("🚀 Starting frame extraction...")
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            # Count extracted frames
            frame_files = list(output_dir.glob(f"{prefix}_*.{self.output_format}"))
            print(f"✅ Successfully extracted {len(frame_files)} frames")
            print(f"📁 Frames saved to: {output_dir}")
            
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"❌ FFmpeg error: {e}")
            print(f"Error output: {e.stderr}")
            return False
    
    def convert_frames_to_ppm(self, input_dir, output_dir="basement_0001a", prefix="r"):
        """
        Convert extracted frames to PPM format for COLMAP
        
        Args:
            input_dir (str): Directory containing extracted frames
            output_dir (str): Directory to save PPM files
            prefix (str): Prefix for PPM filenames (default: "r" for COLMAP)
        """
        input_dir = Path(input_dir)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Find all image files
        image_extensions = ["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.tiff"]
        image_files = []
        for ext in image_extensions:
            image_files.extend(input_dir.glob(ext))
        
        if not image_files:
            print(f"❌ No image files found in {input_dir}")
            return False
        
        print(f"🔄 Converting {len(image_files)} frames to PPM format...")
        
        def convert_single_frame(img_path):
            try:
                # Load image
                img = Image.open(img_path)
                # Convert to RGB if needed
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Generate PPM filename
                ppm_filename = f"{prefix}-{img_path.stem}.ppm"
                ppm_path = output_dir / ppm_filename
                
                # Save as PPM
                img.save(ppm_path, "PPM")
                return f"✅ Converted: {ppm_path}"
                
            except Exception as e:
                return f"❌ Error converting {img_path}: {e}"
        
        # Convert frames in parallel
        max_workers = os.cpu_count() or 4
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(convert_single_frame, img_path) for img_path in image_files]
            for future in as_completed(futures):
                print(future.result())
        
        ppm_files = list(output_dir.glob(f"{prefix}-*.ppm"))
        print(f"\n🎉 Converted {len(ppm_files)} frames to PPM format")
        print(f"📁 PPM files saved to: {output_dir}")
        
        return True
    
    def process_video_to_ppm(self, video_path, output_dir="basement_0001a", prefix="r"):
        """
        Complete pipeline: Video → Frames → PPM files ready for COLMAP
        
        Args:
            video_path (str): Path to input video file
            output_dir (str): Directory to save PPM files
            prefix (str): Prefix for PPM filenames
        """
        print("🎯 Video to PPM Pipeline")
        print("=" * 50)
        
        # Step 1: Extract frames
        temp_dir = "temp_frames"
        if not self.extract_frames(video_path, temp_dir):
            return False
        
        # Step 2: Convert to PPM
        if not self.convert_frames_to_ppm(temp_dir, output_dir, prefix):
            return False
        
        # Clean up temp directory
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        print(f"🧹 Cleaned up temporary directory: {temp_dir}")
        
        print(f"\n✅ Pipeline completed! PPM files ready in: {output_dir}")
        return True


def main():
    """Command line interface"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Convert video to frames using FFmpeg")
    parser.add_argument("video_path", help="Path to input video file")
    parser.add_argument("-f", "--fps", type=int, default=10, help="Frame rate (default: 10)")
    parser.add_argument("-o", "--output", default="extracted_frames", help="Output directory")
    parser.add_argument("-p", "--prefix", default="frame", help="Frame filename prefix")
    parser.add_argument("--format", default="ppm", choices=["ppm", "png", "jpg"], help="Output format")
    parser.add_argument("--to-ppm", action="store_true", help="Convert to PPM format for COLMAP")
    
    args = parser.parse_args()
    
    converter = VideoToFramesConverter(fps=args.fps, output_format=args.format)
    
    if args.to_ppm:
        # Complete pipeline for COLMAP
        converter.process_video_to_ppm(args.video_path, args.output, args.prefix)
    else:
        # Just extract frames
        converter.extract_frames(args.video_path, args.output, args.prefix)


if __name__ == "__main__":
    # Check if command line arguments are provided
    import sys
    if len(sys.argv) > 1:
        # Run command line interface
        main()
    else:
        # Show usage examples
        print("🎬 Video to Frames Converter")
        print("Usage examples:")
        print("1. Extract frames: python video_to_frames.py video.mp4 -f 10")
        print("2. Convert to PPM: python video_to_frames.py video.mp4 --to-ppm")
        print("3. Python usage:")
        print("   from video_to_frames import VideoToFramesConverter")
        print("   converter = VideoToFramesConverter(fps=10)")
        print("   converter.process_video_to_ppm('video.mp4', 'basement_0001a')")
