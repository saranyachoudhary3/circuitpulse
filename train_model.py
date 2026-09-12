import os, sys, shutil, time
from pathlib import Path
import torch

def main():
    ROOT = Path(r"C:\Users\Ayushman\Desktop\circuit_pulse")
    MODELS_DIR = ROOT / "pi_transfer" / "models"
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    from ultralytics import YOLO

    torch.cuda.empty_cache()
    torch.backends.cudnn.benchmark = True
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True

    device = "0"
    print(f"GPU  : {torch.cuda.get_device_name(0)}")
    print(f"VRAM : {round(torch.cuda.get_device_properties(0).total_memory/1e9,1)} GB\n")

    # Base model [1/3] is ALREADY successfully trained and saved to base.pt!
    # Jobs 2 and 3 using local yolov8n.pt (no download needed):
    LOCAL_PRETRAINED = str(ROOT / "yolov8n.pt")

    JOBS = [
        {
            "name": "passives_wire_resistor",
            "data": str(ROOT / "Resistor-Detection--5" / "data.yaml"),
            "pretrained": LOCAL_PRETRAINED,
            "output_name": "passives.pt",
            "epochs": 80,
            "batch": 64,
            "imgsz": 416,
            "workers": 4,
            "desc": "Wire + Resistor + Breadboard (1,596 images)"
        },
        {
            "name": "arduino_components",
            "data": str(ROOT / "Component-Detection-Arduino-UNO-1" / "data.yaml"),
            "pretrained": LOCAL_PRETRAINED,
            "output_name": "arduino.pt",
            "epochs": 80,
            "batch": 64,
            "imgsz": 416,
            "workers": 4,
            "desc": "Arduino board components (630 images)"
        },
    ]

    overall_start = time.time()

    for i, job in enumerate(JOBS, 2):
        data_path = Path(job["data"])
        if not data_path.exists():
            print(f"[{i}/3] SKIP - missing: {data_path}")
            continue

        print(f"\n{'='*72}")
        print(f"[{i}/3] {job['desc']}")
        print(f"  {job['pretrained']} -> {job['output_name']}  |  epochs={job['epochs']}  batch={job['batch']}")
        print(f"{'='*72}")

        torch.cuda.empty_cache()
        t0 = time.time()
        model = YOLO(job["pretrained"])
        model.train(
            data=job["data"],
            epochs=job["epochs"],
            batch=job["batch"],
            imgsz=job["imgsz"],
            device=device,
            workers=job["workers"],
            cache=False,
            amp=True,
            cos_lr=True,
            warmup_epochs=2,
            patience=10,
            save_period=20,
            plots=True,
            project=str(ROOT / "runs" / "detect"),
            name=f"RETRAIN_{job['name']}",
            exist_ok=True,
            mosaic=1.0,
            mixup=0.1,
            degrees=8.0,
            translate=0.1,
            scale=0.4,
            fliplr=0.5,
            hsv_h=0.015,
            hsv_s=0.7,
            hsv_v=0.4,
            verbose=True,
        )

        best = ROOT / "runs" / "detect" / f"RETRAIN_{job['name']}" / "weights" / "best.pt"
        if best.exists():
            dest = MODELS_DIR / job["output_name"]
            bak  = MODELS_DIR / (job["output_name"].replace(".pt", "_prev.pt"))
            if dest.exists():
                shutil.copy2(dest, bak)
            shutil.copy2(best, dest)
            elapsed = round((time.time() - t0) / 60, 1)
            print(f"\n  DONE in {elapsed} min -> {dest}")
        else:
            print(f"  WARNING: best.pt not found at {best}")

    total = round((time.time() - overall_start) / 60, 1)
    print(f"\n{'='*72}")
    print(f"ALL TRAINING COMPLETE! (Jobs 2 & 3 completed in {total} min)")
    print(f"All 3 models ready in {MODELS_DIR}: base.pt, passives.pt, arduino.pt")

if __name__ == "__main__":
    main()
