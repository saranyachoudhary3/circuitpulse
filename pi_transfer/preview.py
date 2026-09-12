import os
import sys
import cv2
from ultralytics import YOLO

camera_url = "http://192.0.0.4:8080/video"
models_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")

modes = {
    "1": ("Components", os.path.join(models_dir, "base.pt")),
    "2": ("Faults", os.path.join(models_dir, "faults.pt")),
    "3": ("Arduino", os.path.join(models_dir, "arduino.pt")),
}

loaded_models = {}
for key, (label, path) in modes.items():
    if os.path.exists(path):
        loaded_models[key] = (label, YOLO(path))

if not loaded_models:
    sys.exit("No models found.")

active_key = "1"
label, model = loaded_models[active_key]

cap = cv2.VideoCapture(camera_url)
if not cap.isOpened():
    sys.exit(f"Failed to open video source at {camera_url}")

print("Preview running. Press 1, 2, 3 to switch mode, or q to quit.")

while True:
    ret, frame = cap.read()
    if not ret:
        cap.release()
        cap = cv2.VideoCapture(camera_url)
        continue

    results = model.predict(frame, conf=0.55, verbose=False)
    annotated = results[0].plot()

    count = len(results[0].boxes)
    cv2.putText(annotated, f"{label} ({count})", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    cv2.imshow("Preview", annotated)

    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break
    elif chr(key) in loaded_models:
        active_key = chr(key)
        label, model = loaded_models[active_key]
        print(f"Switched to {label}")

cap.release()
cv2.destroyAllWindows()
