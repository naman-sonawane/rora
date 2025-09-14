#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

# -------------------------------------------------------------------
# CONFIG (edit here if needed)
# -------------------------------------------------------------------
VIDEO_PATH   = Path("/home/ubuntu/IMG_2604.MOV")   # your video file
WORKDIR      = Path("/home/ubuntu/meshjob")    # where all results go
FPS          = 10                              # frames sampled per second
MAX_FRAMES   = 300                             # cap number of frames


MESHROOM_VERSION = "2025.1.0"
MESHROOM_TGZ_URL = f"https://zenodo.org/records/16887472/files/Meshroom-{MESHROOM_VERSION}-Linux.tar.gz"
MESHROOM_DIRNAME = f"Meshroom-{MESHROOM_VERSION}-Linux"


def run(cmd, env=None, shell=False, check=True):
    print(f"\n$ {' '.join(cmd) if isinstance(cmd, list) else cmd}\n")
    return subprocess.run(cmd, env=env, shell=shell, check=check)

def apt_install(packages):
    try:
        run(["sudo", "apt-get", "update", "-y"])
        run(["sudo", "apt-get", "install", "-y"] + packages)
    except subprocess.CalledProcessError:
        pass

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
    tgz_name = MESHROOM_TGZ_URL.split("/")[-1]
    tgz = workdir / tgz_name
    tgz.parent.mkdir(parents=True, exist_ok=True)

    # Download if missing
    if not tgz.exists():
        run(["wget", "-O", str(tgz), MESHROOM_TGZ_URL])

    # Extract
    run(["tar", "-xzf", str(tgz), "-C", str(workdir)])

    # Find extracted folder
    candidates = [p for p in workdir.iterdir() if p.is_dir() and p.name.startswith("Meshroom-")]
    if not candidates:
        raise FileNotFoundError("❌ Could not find extracted Meshroom directory.")
    target_dir = max(candidates, key=lambda p: p.stat().st_mtime)

    # Search for Meshroom_photogrammetry in all subdirs
    exe = None
    for root, dirs, files in os.walk(target_dir):
        if "Meshroom_photogrammetry" in files:
            exe = Path(root) / "Meshroom_photogrammetry"
            break

    if exe is None:
        raise FileNotFoundError(f"❌ Could not find Meshroom_photogrammetry in {target_dir}")

    exe.chmod(0o755)
    print(f"✅ Found Meshroom_photogrammetry at {exe}")
    return target_dir

def extract_frames(video_path: Path, frames_dir: Path, fps: int, max_frames: int):
    frames_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(frames_dir / "frame_%06d.png")
    run([
        "ffmpeg", "-y", "-i", str(video_path),
        "-vf", f"fps={fps},scale=iw:ih:flags=bicubic",
        pattern
    ])
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
        "--pipeline", "photogrammetry",
        "--descPreset", "high",
        "--photometricMatchingMethod", "L1",
        "--featureQuality", "ultra",
        "--maxPoints", "5000000",
        "--computeDevicesMask", "all",
    ]
    return cmd

def main():
    if not VIDEO_PATH.exists():
        print(f"❌ Video not found: {VIDEO_PATH}")
        sys.exit(1)

    WORKDIR.mkdir(parents=True, exist_ok=True)
    frames_dir = WORKDIR / "frames"
    output_dir = WORKDIR / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("🔧 Ensuring dependencies…")
    ensure_tools()
    ensure_ffmpeg()

    print("🖥️ Detecting GPUs…")
    gpu_ids = detect_gpus()
    print(f"   Found GPUs: {gpu_ids if gpu_ids else 'none'}")

    meshroom_root = download_meshroom(WORKDIR)
    extract_frames(VIDEO_PATH, frames_dir, FPS, MAX_FRAMES)

    graph_json = output_dir / "meshroom_graph.json"
    cmd = build_photogrammetry_cmd(meshroom_root, frames_dir, output_dir, graph_json)

    env = os.environ.copy()
    if gpu_ids:
        env["ALICEVISION_CUDA_DEVICES"] = ",".join(gpu_ids)
        env["CUDA_VISIBLE_DEVICES"] = ",".join(gpu_ids)

    try:
        run(cmd, env=env)
    except subprocess.CalledProcessError:
        print("❌ Meshroom_photogrammetry failed. Check logs above.")
        sys.exit(1)

    cache_texturing = output_dir / "MeshroomCache" / "Texturing"
    final_dir = output_dir / "final"
    final_dir.mkdir(exist_ok=True)
    if cache_texturing.exists():
        candidates = [p for p in cache_texturing.iterdir() if p.is_dir()]
        if candidates:
            latest = max(candidates, key=lambda p: p.stat().st_mtime)
            for ext in ("*.obj", "*.mtl", "*.png"):
                for f in latest.glob(ext):
                    shutil.copy2(f, final_dir / f.name)

    print("\n✅ Done. Final assets are in:", final_dir)

if __name__ == "__main__":
    main()
