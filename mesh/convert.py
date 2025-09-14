from pathlib import Path
from PIL import Image  

input_dir = Path("images")
output_dir = Path("images_jpg")
output_dir.mkdir(exist_ok=True)

# Collect .ppm files sorted
ppm_files = sorted(input_dir.glob("*.ppm"))

for i, ppm_file in enumerate(ppm_files, start=1):
    img = Image.open(ppm_file)
    out_name = output_dir / f"frame_{i:04d}.jpg"
    img.save(out_name, "JPEG")
    print(f"✅ Converted {ppm_file} -> {out_name}")

print(f"\nDone! Converted {len(ppm_files)} files into {output_dir}")
