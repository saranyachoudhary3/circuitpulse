"""
CircuitPulse  Download the BIGGEST, most comprehensive datasets.
1. Roboflow 100 Circuit Elements (46 classes, ~3300 images)
2. Electronic Components by ravi-ranjan-singh (9500+ images)  
3. Basic Electronic Components
"""
import os
import sys

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
    sys.exit(1)

from roboflow import Roboflow

rf = Roboflow(api_key=api_key)

# The BEST comprehensive datasets
mega_datasets = [
    # Roboflow 100 - Circuit Elements (46 classes! THE gold standard)
    ("roboflow-100", "circuit-elements", [6, 5, 4, 3, 2, 1], "RF100 Circuit Elements (46 classes)"),
    
    # Electronic Components - 9500+ images (massive!)
    ("ravi-ranjan-singh", "electronic-components-j5m9z", [3, 2, 1], "Electronic Components 9.5K (ravi-ranjan)"),
    
    # Basic Electronic Components (well-curated)
    ("basic-electronics-components", "basic-electronic-component", [3, 2, 1], "Basic Electronic Components"),
    
    # Another comprehensive one
    ("electronic-components-5mjsu", "electronic-components-rh23n", [3, 2, 1], "Electronic Components Wide v2"),
    
    # Circuit board components  
    ("objectdetectionn", "circuit-board-components", [3, 2, 1], "Circuit Board Components"),
    
    # More component datasets
    ("elec-comp", "electronic-components-detection-bseah", [3, 2, 1], "Electronic Components Detection"),
]

downloaded = []
for ws, proj, versions, name in mega_datasets:
    print(f"\n{'='*60}")
    print(f"Trying: {name}")
    print(f"  workspace={ws}, project={proj}")
    print(f"{'='*60}")
    success = False
    try:
        project = rf.workspace(ws).project(proj)
        for ver in versions:
            try:
                version = project.version(ver)
                dataset = version.download("yolov8")
                print(f"  SUCCESS! v{ver} -> {dataset.location}")
                downloaded.append((name, dataset.location, ver))
                success = True
                break
            except Exception as e:
                err = str(e)[:80]
                print(f"  v{ver}: {err}")
        if not success:
            print(f"  FAILED all versions")
    except Exception as e:
        err = str(e)[:100]
        print(f"  FAILED: {err}")

print(f"\n\nDownloaded {len(downloaded)} datasets:")
for name, loc, ver in downloaded:
    print(f"  {name} (v{ver}): {loc}")
