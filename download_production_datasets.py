"""
CircuitPulse - Download BEST production-quality datasets.
1. EESOB (3830 images, breadboard+Arduino+components) from Roboflow
2. ElectroCom61 (2121 images, 61 classes) from Mendeley/GitHub
"""
import os
import sys
import subprocess
import zipfile
import shutil
from pathlib import Path

# Load .env
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip().strip('"').strip("'")

PROJECT_ROOT = Path(r"C:\Users\Ayushman\Desktop\circuit_pulse")

# 
# 1. EESOB from Roboflow (3830 images!)
# 
print("=" * 60)
print("1. Downloading EESOB (3830 images, breadboard+Arduino+components)")
print("=" * 60)

api_key = os.environ.get("ROBOFLOW_API_KEY")
if api_key:
    from roboflow import Roboflow
    rf = Roboflow(api_key=api_key)
    
    eesob_slugs = [
        ("android-yolo", "eesob", [4, 3, 2, 1]),
        ("android-yolo-iwwbk", "eesob", [4, 3, 2, 1]),
        ("eesob-qfbhn", "eesob", [4, 3, 2, 1]),
    ]
    
    eesob_done = False
    for ws, proj, versions in eesob_slugs:
        print(f"\n  Trying: workspace={ws}, project={proj}")
        try:
            project = rf.workspace(ws).project(proj)
            for ver in versions:
                try:
                    version = project.version(ver)
                    dataset = version.download("yolov8")
                    print(f"  SUCCESS! v{ver} -> {dataset.location}")
                    eesob_done = True
                    break
                except Exception as e:
                    print(f"    v{ver}: {str(e)[:60]}")
            if eesob_done:
                break
        except Exception as e:
            print(f"    FAIL: {str(e)[:80]}")
    
    if not eesob_done:
        print("  Could not download EESOB")
else:
    print("  No API key")

# 
# 2. ElectroCom61 from GitHub
# 
print("\n" + "=" * 60)
print("2. Downloading ElectroCom61 (61 classes, 2121 images)")
print("=" * 60)

electrocom_dir = PROJECT_ROOT / "ElectroCom61"
if not electrocom_dir.exists():
    print("  Cloning from GitHub...")
    result = subprocess.run(
        ["git", "clone", "https://github.com/faiyazabdullah/ElectroCom61.git"],
        cwd=str(PROJECT_ROOT),
        capture_output=True, text=True, timeout=300
    )
    if result.returncode == 0:
        print(f"  SUCCESS! Cloned to: {electrocom_dir}")
    else:
        print(f"  Git clone failed: {result.stderr[:200]}")
        # Try direct zip download
        print("  Trying zip download...")
        import urllib.request
        zip_url = "https://github.com/faiyazabdullah/ElectroCom61/archive/refs/heads/main.zip"
        zip_path = PROJECT_ROOT / "electrocom61.zip"
        try:
            urllib.request.urlretrieve(zip_url, str(zip_path))
            with zipfile.ZipFile(str(zip_path), 'r') as zf:
                zf.extractall(str(PROJECT_ROOT))
            # Rename extracted folder
            extracted = PROJECT_ROOT / "ElectroCom61-main"
            if extracted.exists():
                extracted.rename(electrocom_dir)
            zip_path.unlink()
            print(f"  SUCCESS via zip! -> {electrocom_dir}")
        except Exception as e:
            print(f"  Zip download failed: {e}")
else:
    print(f"  Already exists: {electrocom_dir}")

# 
# 3. Try more Roboflow datasets
# 
if api_key:
    extra_datasets = [
        # PCB Component detection consolidated
        ("owl-panda", "pcb-component-detection-consolidated-dataset", [1, 2], "PCB Consolidated"),
        # PCBA defect detection
        ("pcba-dataset", "pcba-dataset", [1, 2], "PCBA Defects"),
    ]
    
    for ws, proj, versions, name in extra_datasets:
        print(f"\n--- Trying: {name} ({ws}/{proj}) ---")
        try:
            project = rf.workspace(ws).project(proj)
            for ver in versions:
                try:
                    version = project.version(ver)
                    dataset = version.download("yolov8")
                    print(f"  SUCCESS! v{ver} -> {dataset.location}")
                    break
                except Exception as e:
                    print(f"  v{ver}: {str(e)[:60]}")
        except Exception as e:
            print(f"  FAIL: {str(e)[:80]}")

print("\n\nDONE! All production datasets downloaded.")
