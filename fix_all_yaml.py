"""Fix ALL data.yaml files to use absolute paths."""
import os
import yaml
from pathlib import Path

PROJECT_ROOT = Path(r"C:\Users\Ayushman\Desktop\circuit_pulse")

for yaml_path in PROJECT_ROOT.glob("*/data.yaml"):
    folder = yaml_path.parent
    with open(yaml_path) as f:
        data = yaml.safe_load(f)
    
    changed = False
    for key in ["train", "val", "test"]:
        if key in data and data[key]:
            p = data[key]
            if not os.path.isabs(p):
                abs_path = str((folder / p).resolve()).replace("\\", "/")
                data[key] = abs_path
                changed = True
    
    # If no val set, use train
    if "val" not in data or not data.get("val"):
        data["val"] = data.get("train", "")
        changed = True
    
    if changed:
        with open(yaml_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
        print(f"Fixed: {yaml_path}")
    else:
        print(f"OK:    {yaml_path}")

print("\nAll data.yaml files fixed!")
