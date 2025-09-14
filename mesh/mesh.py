#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

MESHROOM_VERSION = "2021.1.0"
MESHROOM_TGZ_URL = f"https://github.com/alicevision/meshroom/releases/download/v{MESHROOM_VERSION}/Meshroom-{MESHROOM_VERSION}-linux.tar.gz"
MESHROOM_DIRNAME = f"Meshroom-{MESHROOM_VERSION}"

def run(cmd, env=None, shell=False, check=True):
    print(f"\n$ {' '.join(cmd) if isinstance(cmd, list) else cmd}\n")
    return subprocess.run(cmd, env=env, shell=shell, check=check)

def apt_install(packages):
    # Idempotent installation (skip if already present)
    try:
        run(["sudo", "apt-get", "update", "-y"])
        run(["sudo", "apt-get", "install", "-y"] + packages)
    except subprocess.CalledProcessError as e:
        print(f"⚠️ apt-get failed (continuing if already installed): {e}")

def ensure_ffmpeg():
    try:
        run(["ffmpeg", "-version"])
    except Exception:
        apt_install(["ffmpeg"])

def ensure_tools():
    apt_install([
        "wget", "tar", "coreutils", "jq", "libgl1", "libx11-6", "libxext6", "libxrender1"
    ])

def detect_gpus():
    try:
        out = subprocess.check_output(["nvidia-smi", "--query-gpu=index", "--format=csv,noheader"]).decode().strip()
        gpus = [g.strip() for g in out.splitlines() if g.strip() != ""]
        return gpus
    except Exception:
        return []

def download_meshroom(workdir: Path):
    # Reuse if already extracted
    target_dir = workdir / MESHROOM_DIRNAME
    if (target_dir / "Meshroom_photogrammetry").exists():
        print("✅ Meshroom already present.")
        return target_dir

    tgz = workdir / f"{MESHROOM_DIRNAME}.tar.gz"
    tgz.parent.mkdir(parents=True, exist_ok=True)
    print("⬇️ Downloading Meshroom headless build…")
    run(["wget", "-O", str(tgz), MESHROOM_TGZ_URL])
    print("📦 Extracting Meshroom…")
    run(["tar", "-xzf", str(tgz), "-C", str(workdir)])
    (target_dir / "Meshroom_photogrammetry").chmod(0o755)
    return target_dir

def extract_frames(video_path: Path, frames_dir: Path, fps: int, max_frames: int):
    frames_dir.mkdir(parents=True, exist_ok=True)
    # Extract densely, then optionally thin to max_frames
    pattern = str(frames_dir / "frame_%06d.png")
    print("🎞️  Extracting frames with FFmpeg…")
    run([
        "ffmpeg", "-y", "-i", str(video_path),
        "-vf", f"fps={fps},scale=iw:ih:flags=bicubic",
        pattern
    ])

    # Enforce max_frames by keeping the first N and removing the rest
    if max_frames is not None and max_frames > 0:
        all_frames = sorted(frames_dir.glob("frame_*.png"))
        if len(all_frames) > max_frames:
            for f in all_frames[max_frames:]:
                f.unlink()
        print(f"🧹 Kept first {max_frames} frames (total now: {len(list(frames_dir.glob('frame_*.png')))}).")

def build_photogrammetry_cmd(meshroom_root: Path, input_dir: Path, output_dir: Path, json_path: Path):
    exe = meshroom_root / "Meshroom_photogrammetry"
    cmd = [
        str(exe),
        "--input", str(input_dir),
        "--output", str(output_dir),
        "--cache", str(output_dir / "cache"),
        "--save", str(json_path),
        # Sensible defaults, tweakable:
        "--pipeline", "photogrammetry",
        "--descPreset", "high",             # feature extraction density
        "--photometricMatchingMethod", "L1",# robust matching
        "--featureQuality", "ultra",        # more features; costs time
        "--maxPoints", "5000000",           # allow large scenes
        "--computeDevicesMask", "all",      # leave to env var for GPUs too
    ]
    return cmd

def main():
    parser = argparse.ArgumentParser(
        description="End-to-end: Video -> frames -> Meshroom (AliceVision) -> textured mesh."
    )
    parser.add_argument("--video", required=True, help="Path to the input video (e.g., /home/ubuntu/input.mp4)")
    parser.add_argument("--workdir", default="/home/ubuntu/meshjob", help="Working directory for everything")
    parser.add_argument("--fps", type=int, default=4, help="Frames per second to sample from the video")
    parser.add_argument("--max-frames", type=int, default=300, help="Limit the number of frames (first N kept)")
    parser.add_argument("--gpus", default="auto", help="Comma-separated GPU IDs (e.g., 0,1,2) or 'auto'")
    args = parser.parse_args()

    video_path = Path(args.video).expanduser().resolve()
    if not video_path.exists():
        print(f"❌ Video not found: {video_path}")
        sys.exit(1)

    workdir = Path(args.workdir).expanduser().resolve()
    frames_dir = workdir / "frames"
    output_dir = workdir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("🔧 Ensuring dependencies…")
    ensure_tools()
    ensure_ffmpeg()

    print("🖥️  Detecting GPUs…")
    detected = detect_gpus()
    print(f"   Detected GPU IDs: {detected if detected else 'none'}")

    # Decide which GPUs to use
    if args.gpus == "auto":
        gpu_ids = detected
    else:
        gpu_ids = [g.strip() for g in args.gpus.split(",") if g.strip() != ""]

    if not gpu_ids:
        print("⚠️ No GPUs found/selected. Meshroom can still run, but CUDA steps will be slow.")
    else:
        print(f"🧠 Using GPUs: {','.join(gpu_ids)}")

    print("📁 Working directory:", workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    # 1) Download Meshroom headless build
    meshroom_root = download_meshroom(workdir)

    # 2) Extract frames
    extract_frames(video_path, frames_dir, args.fps, args.max_frames)

    # 3) Build and run pipeline
    graph_json = output_dir / "meshroom_graph.json"
    cmd = build_photogrammetry_cmd(meshroom_root, frames_dir, output_dir, graph_json)

    # Environment for multi-GPU execution in AliceVision/Meshroom
    env = os.environ.copy()
    if gpu_ids:
        # AliceVision honors these:
        # - ALICEVISION_CUDA_DEVICES: comma-separated GPU IDs
        # - CUDA_VISIBLE_DEVICES: remap visibility to speed up scheduling
        env["ALICEVISION_CUDA_DEVICES"] = ",".join(gpu_ids)
        env["CUDA_VISIBLE_DEVICES"] = ",".join(gpu_ids)
    # Good CPU parallelism defaults
    try:
        import multiprocessing
        env["OMP_NUM_THREADS"] = str(max(1, multiprocessing.cpu_count() - 1))
    except Exception:
        pass

    print("🚀 Starting headless Meshroom pipeline…")
    print("   (This runs SfM → depth maps → meshing → texturing)")
    try:
        run(cmd, env=env)
    except subprocess.CalledProcessError as e:
        print("\n❌ Meshroom_photogrammetry failed.")
        print("   Common causes:\n"
              "   • NVIDIA drivers/CUDA not present or incompatible with this Meshroom build\n"
              "   • Old GLIBC on distro\n"
              "   • Running inside minimal container without GUI libs (we bundled basic X libs)")
        print("   Stdout/Stderr above should show the exact failing node.")
        sys.exit(e.returncode)

    # 4) Locate final assets
    # Meshroom typically writes to output_dir/MeshroomCache/Texturing/<nodeId>/texturedMesh.obj|.mtl|.png
    textured_obj = None
    textured_mtl = None
    textured_png = None

    cache_texturing = output_dir / "MeshroomCache" / "Texturing"
    if cache_texturing.exists():
        # find the most recent node directory
        candidates = [p for p in cache_texturing.iterdir() if p.is_dir()]
        if candidates:
            latest = max(candidates, key=lambda p: p.stat().st_mtime)
            for f in latest.glob("*.obj"):
                textured_obj = f
            for f in latest.glob("*.mtl"):
                textured_mtl = f
            for f in latest.glob("*.png"):
                textured_png = f

    final_dir = output_dir / "final"
    final_dir.mkdir(exist_ok=True)

    copied = []
    for f in [textured_obj, textured_mtl, textured_png]:
        if f and f.exists():
            dst = final_dir / f.name
            shutil.copy2(f, dst)
            copied.append(dst.name)

    print("\n✅ Done.")
    print(f"📦 Output folder: {output_dir}")
    if copied:
        print(f"⭐ Final assets collected in: {final_dir}")
        for name in copied:
            print(f"   - {name}")
    else:
        print("ℹ️ Could not find textured outputs in Texturing cache yet.")
        print("   Check the MeshroomCache within the output directory for node outputs.")
        print(f"   Output JSON graph: {graph_json}")

    # Helpful summary for Unity import
    summary = textwrap.dedent(f"""
    ------------------------------------------------------------
    Unity Import Tips
    ------------------------------------------------------------
    • Import {final_dir}/*.obj (it will reference the .mtl and textures automatically).
    • Ensure the texture (.png) is placed alongside the .obj/.mtl.
    • If scale looks off, apply a uniform scale (OBJ is unitless).
    • For VR scenes, consider light baking after import for better visuals.

    Performance knobs (re-run with different args):
    • --fps          : lower it (e.g., 2) for fewer frames → faster.
    • --max-frames   : cap to 150–300 for speed on big videos.
    • --gpus         : ensure all H100s are listed (e.g., 0,1,2,3,4,5,6,7).
    • Feature/Depth  : change --descPreset to 'normal' for speed (less detail).
    """).strip()
    print(summary)

if __name__ == "__main__":
    main()
