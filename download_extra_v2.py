"""
CircuitPulse  Download additional datasets (attempt 2).
Tries verified Roboflow projects with correct workspace/project slugs.
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

# Try verified PCB defect datasets
datasets_to_try = [
    # YOLOv8 PCB Defects (thesis project - often accessible)
    ("thesis-laxy4", "yolov8-pcb-defects", [1, 2]),
    # PCB dataset defect (object-detection workspace)
    ("object-detection-dt-wzpc6", "pcb-dataset-defect", [1, 2]),
    # Other known public PCB defect projects
    ("pcb-defect-detection-v9i1z", "pcb-defect-detection-biqhf", [1]),
    ("fkui", "pcb-defect-fkui", [1, 2]),
]

pcb_downloaded = False
for ws, proj, versions in datasets_to_try:
    print(f"\nTrying: workspace={ws}, project={proj}")
    try:
        project = rf.workspace(ws).project(proj)
        for ver in versions:
            try:
                version = project.version(ver)
                dataset = version.download("yolov8")
                print(f"SUCCESS! Downloaded version {ver} to: {dataset.location}")
                pcb_downloaded = True
                break
            except Exception as e:
                print(f"  Version {ver} failed: {e}")
        if pcb_downloaded:
            break
    except Exception as e:
        print(f"  Project failed: {e}")

if pcb_downloaded:
    print("\nPCB defect dataset downloaded successfully!")
else:
    print("\nCould not download PCB defect dataset from Roboflow.")
    print("Will proceed with existing datasets only.")
