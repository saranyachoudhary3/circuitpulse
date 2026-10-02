"""
CircuitPulse - Master Training Pipeline
Trains ALL YOLOv8n models on EVERY available dataset using CUDA GPU.
Uses system Python with PyTorch 2.12 + CUDA 12.8 on RTX 5050.

Run with: python train_all_models.py
"""
import os
import sys
import time
import yaml
import shutil
import glob
from pathlib import Path

from ultralytics import YOLO

PROJECT_ROOT = Path(r"C:\Users\Ayushman\Desktop\circuit_pulse")
MODELS_DIR = PROJECT_ROOT / "trained_models"
MODELS_DIR.mkdir(exist_ok=True)


def find_all_datasets():
    """Auto-discover all downloaded datasets with data.yaml files."""
    datasets = []
    for yaml_path in PROJECT_ROOT.glob("*/data.yaml"):
        folder = yaml_path.parent
        with open(yaml_path) as f:
            data = yaml.safe_load(f)
        
        # Count images
        train_path = Path(str(data.get("train", "")).replace("../", str(folder) + "/"))
        if not train_path.is_absolute():
            train_path = folder / data.get("train", "")
        
        img_count = 0
        if train_path.exists():
            img_count = len(list(train_path.glob("*")))
        
        datasets.append({
            "name": folder.name,
            "data_yaml": str(yaml_path),
            "classes": data.get("names", []),
            "nc": data.get("nc", 0),
            "train_images": img_count,
            "folder": str(folder),
        })
    
    # Sort by number of training images (largest first)
    datasets.sort(key=lambda x: x["train_images"], reverse=True)
    return datasets


def fix_data_yaml(yaml_path):
    """Ensure data.yaml has absolute paths."""
    folder = Path(yaml_path).parent
    with open(yaml_path) as f:
        data = yaml.safe_load(f)
    
    changed = False
    for key in ["train", "val", "test"]:
        if key in data and data[key]:
            p = data[key]
            if not os.path.isabs(p):
                # Convert relative to absolute
                abs_path = str(folder / p).replace("\\", "/")
                data[key] = abs_path
                changed = True
    
    if changed:
        with open(yaml_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False)
        print(f"  Fixed paths in {yaml_path}")


def train_model(dataset_info, model_idx):
    """Train a YOLOv8n model on a dataset."""
    name = f"circuitpulse_m{model_idx}_{dataset_info['name']}"
    # Sanitize name for filesystem
    name = name.replace(" ", "_").replace("/", "_")[:60]
    
    data_yaml = dataset_info["data_yaml"]
    
    print(f"\n{'='*70}")
    print(f"MODEL {model_idx}: {dataset_info['name']}")
    print(f"Classes ({dataset_info['nc']}): {dataset_info['classes']}")
    print(f"Training images: {dataset_info['train_images']}")
    print(f"Data YAML: {data_yaml}")
    print(f"{'='*70}")
    
    # Fix data.yaml paths
    fix_data_yaml(data_yaml)
    
    # Determine epochs based on dataset size
    img_count = dataset_info["train_images"]
    if img_count > 2000:
        epochs = 50
        batch = 16
    elif img_count > 500:
        epochs = 60
        batch = 16
    elif img_count > 100:
        epochs = 80
        batch = 16
    else:
        epochs = 100
        batch = 8
    
    print(f"Config: epochs={epochs}, batch={batch}, imgsz=640")
    
    # Load pretrained YOLOv8n
    model = YOLO("yolov8n.pt")
    
    t0 = time.time()
    
    try:
        results = model.train(
            data=data_yaml,
            epochs=epochs,
            imgsz=640,
            batch=batch,
            name=name,
            project=str(PROJECT_ROOT / "runs" / "detect"),
            patience=15,
            save=True,
            save_period=10,
            plots=True,
            verbose=True,
            device=0,  # Force GPU 0
        )
    except Exception as e:
        print(f"\n  ERROR during training: {e}")
        print(f"  Trying with smaller batch size...")
        try:
            results = model.train(
                data=data_yaml,
                epochs=epochs,
                imgsz=640,
                batch=8,  # smaller batch
                name=name,
                project=str(PROJECT_ROOT / "runs" / "detect"),
                patience=15,
                save=True,
                plots=True,
                verbose=True,
                device=0,
            )
        except Exception as e2:
            print(f"  FAILED: {e2}")
            return None, None
    
    elapsed = time.time() - t0
    elapsed_str = f"{elapsed/60:.1f} min"
    
    # Find best.pt
    best_pt = PROJECT_ROOT / "runs" / "detect" / name / "weights" / "best.pt"
    if best_pt.exists():
        dest = MODELS_DIR / f"{name}_best.pt"
        shutil.copy2(best_pt, dest)
        print(f"\n  DONE: {dest}")
        print(f"  Training time: {elapsed_str}")
    else:
        print(f"  WARNING: best.pt not found")
        return None, None
    
    # Validate
    print(f"\n  Validating...")
    try:
        val_model = YOLO(str(best_pt))
        metrics = val_model.val(data=data_yaml, device=0)
        val_results = {
            "mAP50": f"{metrics.box.map50:.4f}",
            "mAP50_95": f"{metrics.box.map:.4f}",
            "precision": f"{metrics.box.mp:.4f}",
            "recall": f"{metrics.box.mr:.4f}",
        }
        print(f"  mAP@50: {val_results['mAP50']} | P: {val_results['precision']} | R: {val_results['recall']}")
    except Exception as e:
        print(f"  Validation error: {e}")
        val_results = None
    
    result = {
        "name": name,
        "dataset": dataset_info["name"],
        "classes": dataset_info["classes"],
        "nc": dataset_info["nc"],
        "train_images": dataset_info["train_images"],
        "epochs": epochs,
        "elapsed": elapsed_str,
        "best_pt": str(best_pt),
        "copied_to": str(dest) if best_pt.exists() else "N/A",
    }
    
    return result, val_results


def write_report(all_results):
    """Write comprehensive training report."""
    report_path = PROJECT_ROOT / "training_report.md"
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# CircuitPulse - Comprehensive Training Report\n\n")
        f.write(f"**Generated:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("---\n\n")
        
        for i, (result, val) in enumerate(all_results, 1):
            if result is None:
                continue
            
            f.write(f"## Model {i}: {result['dataset']}\n\n")
            f.write(f"- **Classes ({result['nc']}):** {', '.join(str(c) for c in result['classes'])}\n")
            f.write(f"- **Training images:** {result['train_images']}\n")
            f.write(f"- **Epochs:** {result['epochs']}\n")
            f.write(f"- **Training time:** {result['elapsed']}\n")
            
            if val:
                f.write(f"- **mAP@50:** {val['mAP50']}\n")
                f.write(f"- **mAP@50-95:** {val['mAP50_95']}\n")
                f.write(f"- **Precision:** {val['precision']}\n")
                f.write(f"- **Recall:** {val['recall']}\n")
            
            f.write(f"- **Weights:** `{result['copied_to']}`\n")
            f.write(f"\n---\n\n")
        
        f.write("## Deployment - Raspberry Pi\n\n")
        f.write("```bash\n")
        f.write("# Copy all models to Pi\n")
        f.write("scp trained_models/*.pt <user>@<pi-ip>:~/circuitpulse/models/\n")
        f.write("```\n\n")
        f.write("```python\n")
        f.write("from ultralytics import YOLO\n")
        f.write("import glob\n\n")
        f.write("# Load all models\n")
        f.write("models = [YOLO(p) for p in glob.glob('models/*_best.pt')]\n\n")
        f.write("# Run inference with all models\n")
        f.write("for model in models:\n")
        f.write("    results = model.predict(frame, conf=0.25)\n")
        f.write("```\n")
    
    print(f"\nReport written to: {report_path}")


if __name__ == "__main__":
    import torch
    print(f"PyTorch: {torch.__version__}")
    print(f"CUDA: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}")
    
    # Find all datasets
    datasets = find_all_datasets()
    
    print(f"\nFound {len(datasets)} datasets:")
    for i, ds in enumerate(datasets, 1):
        print(f"  {i}. {ds['name']} - {ds['train_images']} images, {ds['nc']} classes")
    
    # Train on each
    all_results = []
    for i, ds in enumerate(datasets, 1):
        if ds["train_images"] < 10:
            print(f"\nSkipping {ds['name']} (too few images: {ds['train_images']})")
            continue
        result, val = train_model(ds, i)
        all_results.append((result, val))
    
    write_report(all_results)
    
    print(f"\n{'='*70}")
    print("ALL TRAINING COMPLETE!")
    print(f"{'='*70}")
    print(f"Models saved to: {MODELS_DIR}")
    print(f"Report: {PROJECT_ROOT / 'training_report.md'}")
