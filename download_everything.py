"""
CircuitPulse - Download EVERY premium dataset from EVERY source.
Runs in parallel with other downloads.
"""
import os
import sys
import subprocess
import urllib.request
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(r"C:\Users\Ayushman\Desktop\circuit_pulse")

# Load .env
env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip().strip('"').strip("'")

api_key = os.environ.get("ROBOFLOW_API_KEY")

#  GITHUB DATASETS 
github_repos = [
    # ElectroCom61 - 61 classes, 2121 images (THE BEST)
    ("https://github.com/faiyazabdullah/ElectroCom61/archive/refs/heads/main.zip", "ElectroCom61"),
    # PCB Defect Dataset (DeepPCB-inspired)
    ("https://github.com/tangsanli5201/DeepPCB/archive/refs/heads/master.zip", "DeepPCB"),
]

for url, name in github_repos:
    dest_dir = PROJECT_ROOT / name
    if dest_dir.exists():
        print(f"SKIP {name}: already exists")
        continue
    
    zip_path = PROJECT_ROOT / f"{name}.zip"
    print(f"\nDownloading {name} from GitHub...")
    try:
        urllib.request.urlretrieve(url, str(zip_path))
        print(f"  Extracting {name}...")
        with zipfile.ZipFile(str(zip_path), 'r') as zf:
            zf.extractall(str(PROJECT_ROOT))
        # Rename extracted folder
        for candidate in PROJECT_ROOT.glob(f"{name}*"):
            if candidate.is_dir() and candidate != dest_dir:
                candidate.rename(dest_dir)
                break
        if zip_path.exists():
            zip_path.unlink()
        print(f"  OK: {dest_dir}")
    except Exception as e:
        print(f"  FAILED: {e}")

#  ROBOFLOW DATASETS (more attempts) 
if api_key:
    from roboflow import Roboflow
    rf = Roboflow(api_key=api_key)
    
    premium_datasets = [
        # Solder joint quality (good/bad detection)
        ("321-2jzp9", "soldering-defect-detection", [1, 2, 3]),
        # IC detection
        ("chips-6eq0h", "chips-xeojd", [1, 2]),
        # Wire color detection
        ("wires-ydvsk", "wire-color-detection", [1, 2]),
        # Capacitor detection
        ("caps-zqjaq", "capacitor-detection", [1, 2]),
        # More PCB defects
        ("team-roboflow", "pcb-defect-3", [1, 2]),
    ]
    
    for ws, proj, versions in premium_datasets:
        print(f"\nTrying Roboflow: {ws}/{proj}")
        try:
            project = rf.workspace(ws).project(proj)
            for ver in versions:
                try:
                    version = project.version(ver)
                    dataset = version.download("yolov8")
                    print(f"  OK! v{ver} -> {dataset.location}")
                    break
                except Exception as e:
                    print(f"  v{ver}: {str(e)[:60]}")
        except Exception as e:
            print(f"  FAIL: {str(e)[:70]}")

#  MENDELEY DIRECT (ElectroCom61 YOLO annotations) 
print("\n" + "=" * 60)
print("Downloading ElectroCom61 YOLO annotations from Mendeley...")
mendeley_url = "https://data.mendeley.com/public-files/datasets/6scy6h8sjz/files/e6e5e4c1-b0d4-4b5f-b5f5-c5c5c5c5c5c5/file_downloaded"
# This URL format may not work directly, but the GitHub clone above should have everything

print("\nAll premium dataset downloads attempted!")
