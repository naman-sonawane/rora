from pathlib import Path
from PIL import Image
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import subprocess

# Paths
DATASET_ROOT = Path("basement_0001a").expanduser()   # Folder from unzip
OUTPUT_ROOT = Path("converted").expanduser()         # Where PNGs will go
WORKSPACE = "colmap_output"                          # Where COLMAP results go
DATABASE_PATH = os.path.join(WORKSPACE, "database.db")
SPARSE_PATH = os.path.join(WORKSPACE, "sparse")
DENSE_PATH = os.path.join(WORKSPACE, "dense")


def convert_single(ppm):
    try:
        img = Image.open(ppm).convert("RGB")
        out_name = f"{ppm.parent.name}__{ppm.stem}.png"
        out_file = OUTPUT_ROOT / out_name
        img.save(out_file, "PNG")
        return f"✅ Converted: {out_file}"
    except Exception as e:
        return f"❌ Error on {ppm}: {e}"


def convert_ppm_to_png():
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    ppm_files = list(DATASET_ROOT.rglob("r-*.ppm"))
    if not ppm_files:
        print(f"❌ No .ppm files found in {DATASET_ROOT}")
        return

    print(f"🔍 Found {len(ppm_files)} PPM files. Starting parallel conversion...")

    max_workers = os.cpu_count() or 8
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(convert_single, ppm) for ppm in ppm_files]
        for future in as_completed(futures):
            print(future.result())

    print(f"\n🎉 All PNGs are in: {OUTPUT_ROOT}\n")


def run_colmap():
    os.makedirs(SPARSE_PATH, exist_ok=True)
    os.makedirs(DENSE_PATH, exist_ok=True)

    print("🚀 Starting COLMAP Feature Extraction (GPU)...")
    subprocess.run([
        "colmap", "feature_extractor",
        "--database_path", DATABASE_PATH,
        "--image_path", str(OUTPUT_ROOT),
        "--FeatureExtraction.use_gpu", "1",
        "--FeatureExtraction.gpu_index", "0",
        "--FeatureExtraction.num_threads", "-1"
    ], check=True)

    print("🔗 Matching Features...")
    subprocess.run([
        "colmap", "exhaustive_matcher",
        "--database_path", DATABASE_PATH
    ], check=True)

    print("🧠 Sparse Reconstruction (Mapper)...")
    subprocess.run([
        "colmap", "mapper",
        "--database_path", DATABASE_PATH,
        "--image_path", str(OUTPUT_ROOT),
        "--output_path", SPARSE_PATH
    ], check=True)

    print("🧼 Undistorting Images...")
    subprocess.run([
        "colmap", "image_undistorter",
        "--image_path", str(OUTPUT_ROOT),
        "--input_path", os.path.join(SPARSE_PATH, "0"),
        "--output_path", DENSE_PATH,
        "--output_type", "COLMAP"
    ], check=True)

    print("🧱 Dense Reconstruction (PatchMatch Stereo, CUDA build)...")
    subprocess.run([
        "colmap", "patch_match_stereo",
        "--workspace_path", DENSE_PATH,
        "--workspace_format", "COLMAP",
        "--PatchMatchStereo.geom_consistency", "true",
        "--PatchMatchStereo.gpu_index", "0"
    ], check=True)

    print("🔄 Fusing Point Clouds...")
    subprocess.run([
        "colmap", "stereo_fusion",
        "--workspace_path", DENSE_PATH,
        "--workspace_format", "COLMAP",
        "--input_type", "geometric",
        "--output_path", os.path.join(DENSE_PATH, "fused.ply")
    ], check=True)

    print("\n✅ Mesh created at:", os.path.join(DENSE_PATH, "fused.ply"))



if __name__ == "__main__":
    convert_ppm_to_png()
    run_colmap()
