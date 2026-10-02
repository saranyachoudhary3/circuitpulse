"""
CircuitPulse  Download additional datasets for fault/defect detection.
Dataset 3: PCB Defect Detection  classes: short, open circuit, missing hole, mouse bite, spur, spurious copper
Dataset 4: Circuit Components (broader)  breadboard-level components with LED, Arduino, etc.
"""
import os
import sys

# Load .env
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
import time

rf = Roboflow(api_key=api_key)

#  Dataset 3: PCB Defect Detection (fault classes) 
# This is the well-known PCB defect dataset with: missing_hole, mouse_bite, open_circuit, short, spur, spurious_copper
datasets_to_try = [
    {
        "name": "PCB Defects (Augmented Startups)",
        "workspace": "augmented-startups",
        "project": "pcb-defects",
        "versions": [2, 1],
    },
    {
        "name": "PCB Defect Detection (longht)",
        "workspace": "longht",
        "project": "pcb-dataset-defect",
        "versions": [2, 1],
    },
    {
        "name": "PCB Defect (tangseng)",
        "workspace": "tangseng",
        "project": "pcb-defect",
        "versions": [2, 1],
    },
    {
        "name": "PCB Defect Detection Ultra",
        "workspace": "project-doplv",
        "project": "pcb-defect-detection-ultra",
        "versions": [1],
    },
]

pcb_downloaded = False
for ds in datasets_to_try:
    print(f"\n{'='*60}")
    print(f"Trying: {ds['name']}")
    print(f"  workspace={ds['workspace']}, project={ds['project']}")
    print(f"{'='*60}")
    try:
        project = rf.workspace(ds["workspace"]).project(ds["project"])
        for ver in ds["versions"]:
            try:
                version = project.version(ver)
                dataset = version.download("yolov8")
                print(f" Downloaded version {ver} to: {dataset.location}")
                pcb_downloaded = True
                break
            except Exception as e:
                print(f"  Version {ver} failed: {e}")
        if pcb_downloaded:
            break
    except Exception as e:
        print(f"  Project failed: {e}")

if not pcb_downloaded:
    print("\nWARNING: Could not download any PCB defect dataset")

#  Dataset 4: Circuit Component Detection (broader  with LEDs, Arduino, etc.) 
component_datasets = [
    {
        "name": "Circuit Component Detection (jbhepner)",
        "workspace": "jbhepner",
        "project": "component-detection-yolov8",
        "versions": [3, 2, 1],
    },
    {
        "name": "EESOB Electronic Components",
        "workspace": "eesob",
        "project": "eesob",
        "versions": [3, 2, 1],
    },
    {
        "name": "Circuit Components (broader)",
        "workspace": "circuit-elements-detection",
        "project": "circuit-components-detection",
        "versions": [3, 2, 1],
    },
]

comp_downloaded = False
for ds in component_datasets:
    print(f"\n{'='*60}")
    print(f"Trying: {ds['name']}")
    print(f"  workspace={ds['workspace']}, project={ds['project']}")
    print(f"{'='*60}")
    try:
        project = rf.workspace(ds["workspace"]).project(ds["project"])
        for ver in ds["versions"]:
            try:
                version = project.version(ver)
                dataset = version.download("yolov8")
                print(f" Downloaded version {ver} to: {dataset.location}")
                comp_downloaded = True
                break
            except Exception as e:
                print(f"  Version {ver} failed: {e}")
        if comp_downloaded:
            break
    except Exception as e:
        print(f"  Project failed: {e}")

if not comp_downloaded:
    print("\nWARNING: Could not download any broader component dataset")

print("\n Additional dataset download complete!")
