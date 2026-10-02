"""
CircuitPulse  Download MORE comprehensive datasets for complete fault coverage.
Tries every available circuit/component/fault dataset on Roboflow.
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

# Comprehensive list of datasets to try
datasets = [
    # Solder defect detection
    ("321-2jzp9", "soldering-defect-detection", [1, 2, 3], "Solder Defect Detection"),
    ("pet-project-k4yxb", "soldering-defect-model", [1, 2], "Soldering Defect Model"),
    
    # PCB solder defects (larger)
    ("pcb-solder-defect-detection", "pcb-solder-defect-detection", [1, 2], "PCB Solder Defect V1"),
    ("solder-joint-defects", "solder-joint-defects", [1, 2], "Solder Joint Defects"),
    
    # Circuit component detection (Arduino, breadboard focused)
    ("tanish", "component-detection-arduino-uno", [1, 2, 3], "Arduino Component Detection"),
    
    # Broader electronic components
    ("electronic-component-kfv3w", "electronic-component", [1, 2], "Electronic Component Detection"),
    ("electronic-components-mz5kd", "electronic-components", [1, 2, 3], "Electronic Components Wide"),
    
    # Wire/cable detection
    ("wire-detection-sfxdz", "wire-detection", [1, 2], "Wire Detection"),
    
    # Circuit board inspection
    ("circuit-board-defect", "circuit-board-defect", [1, 2], "Circuit Board Defect"),
    ("circuit-board-qc", "circuit-board-qc", [1, 2], "Circuit Board QC"),
    
    # LED detection specifically
    ("led-detection-tczwu", "led-detection", [1, 2], "LED Detection"),
]

downloaded = []
failed = []

for ws, proj, versions, name in datasets:
    print(f"\n--- Trying: {name} ({ws}/{proj}) ---")
    success = False
    try:
        project = rf.workspace(ws).project(proj)
        for ver in versions:
            try:
                version = project.version(ver)
                dataset = version.download("yolov8")
                print(f"  OK: Downloaded v{ver} -> {dataset.location}")
                downloaded.append((name, dataset.location))
                success = True
                break
            except Exception as e:
                err = str(e)
                if "not a zip" in err.lower():
                    print(f"  v{ver}: corrupt zip, skip")
                elif "not found" in err.lower():
                    print(f"  v{ver}: not found, try next")
                else:
                    print(f"  v{ver}: {err[:80]}")
        if not success:
            failed.append(name)
    except Exception as e:
        err = str(e)[:100]
        print(f"  FAIL: {err}")
        failed.append(name)

print("\n" + "=" * 60)
print("DOWNLOAD SUMMARY")
print("=" * 60)
print(f"\nDownloaded ({len(downloaded)}):")
for name, loc in downloaded:
    print(f"  - {name}: {loc}")
print(f"\nFailed ({len(failed)}):")
for name in failed:
    print(f"  - {name}")
