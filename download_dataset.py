"""
CircuitPulse  Download datasets from Roboflow Universe.
Reads ROBOFLOW_API_KEY from environment variable or .env file.
"""
import os
import sys
import time

env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip().strip('"').strip("'")

api_key = os.environ.get("ROBOFLOW_API_KEY")
if not api_key:
    print("ERROR: ROBOFLOW_API_KEY not set.")
    print("Set it via:  $env:ROBOFLOW_API_KEY = 'your_key_here'")
    print("Or create a .env file with:  ROBOFLOW_API_KEY=your_key_here")
    sys.exit(1)

from roboflow import Roboflow

rf = Roboflow(api_key=api_key)

print("\n" + "=" * 60)
print("Downloading PRIMARY dataset: Resistor Detection")
print("=" * 60)
t0 = time.time()
try:
    project = rf.workspace("circuits-project").project("resistor-detection-5azes")
    # Try version 5 first, fall back to other versions
    dataset = None
    for ver in [5, 4, 3, 2, 1]:
        try:
            version = project.version(ver)
            dataset = version.download("yolov8")
            print(f" Downloaded version {ver} to: {dataset.location}")
            break
        except Exception as e:
            print(f"  Version {ver} failed: {e}, trying next...")
    if dataset is None:
        print("ERROR: Could not download any version of the primary dataset!")
        sys.exit(1)
    elapsed = time.time() - t0
    print(f"  Download time: {elapsed:.1f}s")
except Exception as e:
    print(f"ERROR downloading primary dataset: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("Downloading SECONDARY dataset: Electronics Components")
print("=" * 60)
t1 = time.time()
try:
    project2 = rf.workspace("jovine").project("electronics-components")
    dataset2 = None
    for ver in [3, 2, 1]:
        try:
            version2 = project2.version(ver)
            dataset2 = version2.download("yolov8")
            print(f" Downloaded version {ver} to: {dataset2.location}")
            break
        except Exception as e:
            print(f"  Version {ver} failed: {e}, trying next...")
    if dataset2 is None:
        print("WARNING: Could not download secondary dataset (stretch goal only)")
    else:
        elapsed2 = time.time() - t1
        print(f"  Download time: {elapsed2:.1f}s")
except Exception as e:
    print(f"WARNING: Secondary dataset download failed: {e}")
    print("  (This is the stretch goal  not critical)")

print("\n Dataset download complete!")
