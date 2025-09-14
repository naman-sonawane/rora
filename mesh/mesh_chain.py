#!/bin/bash

# Video-to-3D Pipeline Script
# Usage: ./video_to_3d.sh <images_directory> [scene_name]

set -e  # Exit on any error

IMAGES_DIR="$1"
SCENE_NAME="${2:-my_scene}"
COLMAP_EXE="~/colmap/build/src/colmap/exe/colmap"
NGP_DIR="~/instant-ngp"

# Expand paths
COLMAP_EXE=$(eval echo $COLMAP_EXE)
NGP_DIR=$(eval echo $NGP_DIR)

echo "=================================================="
echo "VIDEO-TO-3D PIPELINE"
echo "=================================================="
echo "Images: $IMAGES_DIR"
echo "Scene: $SCENE_NAME"  
echo "COLMAP: $COLMAP_EXE"
echo "Instant-NGP: $NGP_DIR"
echo "=================================================="

# Check inputs
if [ ! -d "$IMAGES_DIR" ]; then
    echo "ERROR: Images directory $IMAGES_DIR does not exist"
    exit 1
fi

if [ ! -f "$COLMAP_EXE" ]; then
    echo "ERROR: COLMAP executable not found at $COLMAP_EXE"
    exit 1
fi

cd "$NGP_DIR"

# Set environment for headless operation
export QT_QPA_PLATFORM=offscreen

echo "[1/8] Setting up scene directory..."
rm -rf data/$SCENE_NAME
mkdir -p data/$SCENE_NAME/images
cp "$IMAGES_DIR"/* data/$SCENE_NAME/images/
echo "Copied $(ls data/$SCENE_NAME/images/ | wc -l) images"

echo "[2/8] Extracting features..."
rm -f colmap.db colmap_sparse colmap_text
$COLMAP_EXE feature_extractor \
    --database_path colmap.db \
    --image_path data/$SCENE_NAME/images \
    --ImageReader.single_camera 1

echo "[3/8] Matching features (GPU accelerated)..."
$COLMAP_EXE exhaustive_matcher \
    --database_path colmap.db \
    --FeatureMatching.use_gpu=1 \
    --FeatureMatching.gpu_index=0

echo "[4/8] Running 3D reconstruction..."
mkdir -p colmap_sparse
$COLMAP_EXE mapper \
    --database_path colmap.db \
    --image_path data/$SCENE_NAME/images \
    --output_path colmap_sparse \
    --Mapper.ba_use_gpu=1 \
    --Mapper.ba_gpu_index=0

echo "[5/8] Converting to text format..."
mkdir -p colmap_text
$COLMAP_EXE model_converter \
    --input_path colmap_sparse/0 \
    --output_path colmap_text \
    --output_type TXT

echo "[6/8] Generating transforms.json..."
python3 scripts/colmap2nerf.py \
    --text colmap_text \
    --images data/$SCENE_NAME/images \
    --out data/$SCENE_NAME/transforms.json

# Fix image paths in transforms.json
echo "Fixing image paths in transforms.json..."
sed -i 's|"file_path": "\./data/'$SCENE_NAME'/|"file_path": "|g' data/$SCENE_NAME/transforms.json

echo "[7/8] Training Instant-NGP..."
python3 - <<EOF
import sys, os, numpy as np, time
sys.path.append('$NGP_DIR/build')
import pyngp as ngp

try:
    import trimesh
    HAVE_TRIMESH = True
except ImportError:
    HAVE_TRIMESH = False
    print("WARNING: trimesh not available")

# Training parameters
MAX_STEPS = 35000
TARGET_LOSS = 1e-4

print("Loading training data...")
tb = ngp.Testbed()
tb.load_training_data("data/$SCENE_NAME")
tb.shall_train = True

print(f"Training for up to {MAX_STEPS} steps...")
start_time = time.time()

for step in range(MAX_STEPS):
    tb.frame()
    
    if step % 1000 == 0:
        try:
            loss = tb.loss
            elapsed = time.time() - start_time
            print(f"Step {step:6d}: loss = {loss:.6f} ({elapsed:.1f}s)")
            
            if loss < TARGET_LOSS:
                print(f"Target loss reached at step {step}")
                break
        except:
            pass

tb.save_snapshot("trained_model.msgpack")
print("Training complete!")

print("[8/8] Exporting meshes...")

# Export multiple quality levels
configs = [
    (512, 20.0, "medium"),
    (768, 15.0, "high"), 
    (1024, 10.0, "ultra")
]

for res, threshold, quality in configs:
    filename = f"mesh_{quality}_r{res}_t{threshold:.0f}.obj"
    res_array = np.array([res, res, res], dtype=np.int32)
    
    try:
        tb.compute_and_save_marching_cubes_mesh(
            filename, res_array, tb.render_aabb, float(threshold)
        )
        
        if os.path.exists(filename):
            size = os.path.getsize(filename)
            print(f"Exported {filename}: {size:,} bytes")
            
            # Clean mesh if trimesh available
            if HAVE_TRIMESH and size > 1000:
                try:
                    mesh = trimesh.load(filename, force='mesh')
                    if isinstance(mesh, trimesh.Scene):
                        geometries = list(mesh.geometry.values())
                        if geometries:
                            mesh = trimesh.util.concatenate(geometries)
                    
                    components = mesh.split(only_watertight=False)
                    if components:
                        largest = max(components, key=lambda x: len(x.vertices))
                        largest.remove_duplicate_faces()
                        largest.remove_unreferenced_vertices()
                        
                        clean_name = filename.replace('.obj', '_clean.obj')
                        largest.export(clean_name)
                        clean_size = os.path.getsize(clean_name)
                        print(f"Cleaned {clean_name}: {clean_size:,} bytes")
                except Exception as e:
                    print(f"Cleaning failed for {filename}: {e}")
    except Exception as e:
        print(f"Export failed for {filename}: {e}")

EOF

echo "=================================================="
echo "PIPELINE COMPLETE!"
echo "=================================================="
echo "Generated files:"
ls -la *.obj *.msgpack 2>/dev/null || echo "No mesh files found"
echo ""
echo "For Unity:"
echo "1. Use mesh_medium_* for VR (good performance)"
echo "2. Use mesh_high_* for desktop (better quality)"  
echo "3. Try *_clean.obj versions first"
echo "=================================================="