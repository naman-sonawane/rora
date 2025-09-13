from pathlib import Path
from PIL import Image
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

# Paths
DATASET_ROOT = Path("basement_0001a").expanduser()
OUTPUT_ROOT = Path("converted").expanduser()

def convert(ppm: Path):
    try:
        img = Image.open(ppm).convert("RGB")
        out_name = f"{ppm.parent.name}__{ppm.stem}.png"
        out_file = OUTPUT_ROOT / out_name
        img.save(out_file, "PNG")
        return f"✅ {out_file}"
    except Exception as e:
        return f"❌ Error on {ppm}: {e}"

def main():
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    ppm_files = list(DATASET_ROOT.rglob("r-*.ppm"))
    if not ppm_files:
        print(f"❌ No .ppm files found in {DATASET_ROOT}")
        return

    print(f"🔍 Found {len(ppm_files)} PPM files. Starting parallel conversion...")

    # Use all available CPU threads
    max_workers = os.cpu_count() or 8

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(convert, ppm) for ppm in ppm_files]
        for future in as_completed(futures):
            print(future.result())

    print(f"\n🎉 Done! All PNGs are in {OUTPUT_ROOT}")

if __name__ == "__main__":
    main()
