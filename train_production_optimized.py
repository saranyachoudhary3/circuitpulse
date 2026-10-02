import os
from ultralytics import YOLO

def main():
    print("Initializing Pi-5 Optimized Training Pipeline...")
    
    # Check if YOLO11 is available, fallback to YOLOv8s if ultralytics version is older
    try:
        model = YOLO("yolo11s.pt")
        print("Successfully loaded yolo11s.pt")
    except Exception as e:
        print(f"YOLO11s not found or unsupported ({e}). Falling back to yolov8s.pt")
        model = YOLO("yolov8s.pt")
        
    print("Starting training with aggressive augmentations...")
    # Train the model
    model.train(
        data=os.path.abspath("Merged-Dataset/data.yaml"),
        epochs=100,
        imgsz=640,
        batch=16, # Suitable for RTX 5050
        device="0",
        patience=20,
        project="ProductionRun",
        name="circuit_master_optimized",
        # Aggressive augmentations
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.4,
        degrees=10.0,
        translate=0.1,
        scale=0.5,
        perspective=0.001,
        mosaic=1.0,
        mixup=0.1
    )
    
    print("Training Complete. Exporting to NCNN INT8 format for Raspberry Pi 5...")
    try:
        # Export to NCNN with INT8 quantization
        # Requires the dataset to calibrate the quantization ranges
        model.export(format="ncnn", int8=True, data=os.path.abspath("Merged-Dataset/data.yaml"))
        print("Export successful!")
    except Exception as e:
        print(f"INT8 export failed: {e}. Falling back to standard NCNN FP16 export.")
        model.export(format="ncnn", half=True)

if __name__ == "__main__":
    main()
