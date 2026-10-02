"""
CircuitPulse - MAX SPEED Production Training
Optimized for fastest training on RTX 5050 (8GB VRAM).
- batch=32 (use more GPU)
- cache='ram' (load all images into RAM for zero disk I/O)
- workers=8 (parallel CPU data loading)
- AMP enabled (half-precision = 2x speed)
- Reduced epochs with aggressive early stopping
"""
import time
import shutil
from pathlib import Path
import yaml
import os


def main():
    import torch
    from ultralytics import YOLO

    PROJECT_ROOT = Path(r"C:\Users\Ayushman\Desktop\circuit_pulse")
    MODELS_DIR = PROJECT_ROOT / "trained_models"
    MODELS_DIR.mkdir(exist_ok=True)

    print(f"PyTorch: {torch.__version__}")
    print(f"CUDA: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        vram = torch.cuda.get_device_properties(0).total_memory / 1024**3
        print(f"VRAM: {vram:.1f} GB")

    # Speed optimization configs
    SPEED_CONFIG = dict(
        imgsz=640,
        batch=64,           # Max batch -> fills ~6-7GB of 8GB VRAM
        cache="disk",        # Cache to disk (train needs 19GB RAM, only 12GB free)
        workers=0,           # Windows multiprocessing limitation
        amp=True,            # Mixed precision -> 2x GPU throughput
        device=0,            # GPU 0
        patience=12,         # Slightly less patience for faster convergence
        save=True,
        save_period=-1,      # Only save best/last (no checkpoints = faster)
        plots=True,
        verbose=True,
        augment=True,
        mosaic=1.0,
        mixup=0.1,
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.4,
        degrees=10.0,
        translate=0.1,
        scale=0.5,
        fliplr=0.5,
    )

    configs = [
        {
            "name": "PRODUCTION_eesob_48class",
            "yaml": str(PROJECT_ROOT / "EESOB-4" / "data.yaml"),
            "epochs": 60,  # 8322 images, enough for convergence
            "desc": "EESOB - 48 Components (8322 images)",
        },
        {
            "name": "PRODUCTION_pcb_faults",
            "yaml": str(PROJECT_ROOT / "yolov8-pcb-defects-1" / "data.yaml"),
            "epochs": 80,  # Smaller dataset needs more epochs
            "desc": "PCB Faults - 6 Classes (500 images)",
        },
        {
            "name": "PRODUCTION_circuit_elements",
            "yaml": str(PROJECT_ROOT / "circuit-elements-4" / "data.yaml"),
            "epochs": 60,
            "desc": "Circuit Elements RF100 - 31 Classes (672 images)",
        },
    ]

    all_results = []
    total_t0 = time.time()

    for cfg in configs:
        yaml_path = cfg["yaml"]

        # Fix paths if needed
        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        # Verify train path exists
        train_path = data.get("train", "")
        if not train_path or not Path(train_path).exists():
            folder = Path(yaml_path).parent
            data["train"] = str(folder / "train" / "images")
            data["val"] = str(folder / "valid" / "images")
            test_path = folder / "test" / "images"
            if test_path.exists():
                data["test"] = str(test_path)
            with open(yaml_path, "w") as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
            print(f"Fixed paths for {cfg['name']}")

        # Verify again
        final_train = data.get("train", str(Path(yaml_path).parent / "train" / "images"))
        if not Path(final_train).exists():
            print(f"\nSKIPPING {cfg['name']}: train path not found at {final_train}")
            continue

        print(f"\n{'='*70}")
        print(f"TRAINING: {cfg['desc']}")
        print(f"Speed: batch=32, cache=RAM, workers=8, AMP=True")
        print(f"{'='*70}")

        model = YOLO("yolov8n.pt")
        t0 = time.time()

        try:
            results = model.train(
                data=yaml_path,
                epochs=cfg["epochs"],
                name=cfg["name"],
                project=str(PROJECT_ROOT / "runs" / "detect"),
                **SPEED_CONFIG,
            )
        except RuntimeError as e:
            if "out of memory" in str(e).lower():
                print(f"\n  OOM with batch=64, retrying with batch=32...")
                torch.cuda.empty_cache()
                speed_cfg_small = SPEED_CONFIG.copy()
                speed_cfg_small["batch"] = 32
                model = YOLO("yolov8n.pt")
                results = model.train(
                    data=yaml_path,
                    epochs=cfg["epochs"],
                    name=cfg["name"],
                    project=str(PROJECT_ROOT / "runs" / "detect"),
                    **speed_cfg_small,
                )
            else:
                print(f"  ERROR: {e}")
                continue

        elapsed = time.time() - t0
        print(f"\n  Done in {elapsed/60:.1f} min")

        # Save best.pt
        best_pt = PROJECT_ROOT / "runs" / "detect" / cfg["name"] / "weights" / "best.pt"
        if best_pt.exists():
            dest = MODELS_DIR / f"{cfg['name']}_best.pt"
            shutil.copy2(best_pt, dest)
            print(f"  Saved: {dest}")

            # Quick validation
            val_model = YOLO(str(best_pt))
            metrics = val_model.val(data=yaml_path, device=0, workers=0)
            result_info = {
                "name": cfg["name"],
                "desc": cfg["desc"],
                "elapsed": f"{elapsed/60:.1f} min",
                "mAP50": f"{metrics.box.map50:.4f}",
                "mAP50_95": f"{metrics.box.map:.4f}",
                "precision": f"{metrics.box.mp:.4f}",
                "recall": f"{metrics.box.mr:.4f}",
            }
            all_results.append(result_info)
            print(f"  mAP@50: {result_info['mAP50']} | P: {result_info['precision']} | R: {result_info['recall']}")

    total_elapsed = (time.time() - total_t0) / 60
    print(f"\n{'='*70}")
    print(f"ALL PRODUCTION TRAINING COMPLETE in {total_elapsed:.0f} minutes!")
    print(f"{'='*70}")

    # List all models
    all_models = sorted(MODELS_DIR.glob("*.pt"))
    print(f"\nAll models ({len(all_models)}):")
    for m in all_models:
        size_mb = m.stat().st_size / 1024 / 1024
        tag = " *** PRODUCTION ***" if "PRODUCTION" in m.name else ""
        print(f"  {m.name} ({size_mb:.1f} MB){tag}")

    # Write comprehensive report
    report = PROJECT_ROOT / "training_report.md"
    with open(report, "w", encoding="utf-8") as f:
        f.write("# CircuitPulse - Production Training Report\n\n")
        f.write(f"**Generated:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**Total training time:** {total_elapsed:.0f} minutes\n")
        f.write(f"**GPU:** NVIDIA GeForce RTX 5050 Laptop GPU (8 GB VRAM)\n\n")
        f.write("---\n\n")

        for r in all_results:
            f.write(f"## {r['desc']}\n\n")
            f.write(f"| Metric | Value |\n")
            f.write(f"|--------|-------|\n")
            f.write(f"| Training time | {r['elapsed']} |\n")
            f.write(f"| mAP@50 | {r['mAP50']} |\n")
            f.write(f"| mAP@50-95 | {r['mAP50_95']} |\n")
            f.write(f"| Precision | {r['precision']} |\n")
            f.write(f"| Recall | {r['recall']} |\n")
            f.write(f"| Weights | `trained_models/{r['name']}_best.pt` |\n\n")

        f.write("---\n\n## All Trained Models\n\n")
        f.write("| Model | Size | Type |\n|-------|------|------|\n")
        for m in all_models:
            size_mb = m.stat().st_size / 1024 / 1024
            mtype = "PRODUCTION" if "PRODUCTION" in m.name else "Standard"
            f.write(f"| `{m.name}` | {size_mb:.1f} MB | {mtype} |\n")

        f.write("\n---\n\n## Deployment to Raspberry Pi\n\n")
        f.write("```bash\n# Copy production models to Pi\n")
        f.write("scp trained_models/PRODUCTION_*.pt user@<pi-ip>:~/circuitpulse/models/\n```\n\n")
        f.write("```python\nfrom ultralytics import YOLO\n\n")
        f.write("# Load production models\n")
        f.write('component_model = YOLO("models/PRODUCTION_eesob_48class_best.pt")  # 48 components\n')
        f.write('fault_model = YOLO("models/PRODUCTION_pcb_faults_best.pt")          # 6 fault types\n')
        f.write('circuit_model = YOLO("models/PRODUCTION_circuit_elements_best.pt")  # 31 elements\n\n')
        f.write("# Real-time inference from camera\n")
        f.write('results = component_model.predict(source=0, show=True, conf=0.25)\n')
        f.write("```\n")

    print(f"\nReport: {report}")


if __name__ == "__main__":
    main()
