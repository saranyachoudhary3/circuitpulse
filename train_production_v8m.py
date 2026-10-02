from ultralytics import YOLO

def main():
    print("Initializing Production-Grade YOLOv8 Medium Training Pipeline...")
    
    # YOLOv8m (Medium) is much more robust than the Small/Nano models we used previously.
    # It has 25.9M parameters (compared to 3.2M in Nano), giving it the capacity to 
    # learn the complex topological features of jumper wires and tiny resistor bands.
    model = YOLO("yolov8m.pt")
    
    # We are using the massive dataset you already aggregated, but we are injecting 
    # hyper-parameters for intense augmentation to solve the glare/focus issues physically.
    model.train(
        data="Merged-Dataset/data.yaml",
        epochs=100,              # Deep training
        imgsz=640,               # Higher resolution (640x640 instead of 320x320)
        batch=16,                # Adjust based on your RTX 5050 VRAM
        device="0",              # Force NVIDIA GPU
        patience=20,             # Early stopping
        save=True,               
        project="ProductionRun",
        name="circuit_master_v8m",
        # --- PRODUCTION AUGMENTATIONS ---
        hsv_h=0.015,             # Hue augmentation
        hsv_s=0.7,               # Saturation augmentation (helps with glare washout)
        hsv_v=0.4,               # Value augmentation (simulates varying room lighting)
        degrees=10.0,            # Small rotations
        translate=0.1,           # Translation
        scale=0.5,               # Scale variance
        perspective=0.001,       # Perspective warping (simulates off-angle camera)
        flipud=0.5,              # Flip up-down
        fliplr=0.5,              # Flip left-right
        mosaic=1.0,              # 100% Mosaic augmentation for dense layouts
        mixup=0.1                # Mixup to generalize background noise
    )
    
    print("Training Complete. Exporting to NCNN for Raspberry Pi 5...")
    model.export(format="ncnn", half=True) # FP16 quantization for Pi speed

if __name__ == "__main__":
    main()
