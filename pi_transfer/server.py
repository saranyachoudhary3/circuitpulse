import os
import base64
from datetime import datetime

import cv2
import numpy as np
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from ultralytics import YOLO

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")
CAMERA_URL = "http://192.0.0.4:8080/video"
PORT = 5000

print("[INFO] Loading detection models...")
models = {
    "components": YOLO(os.path.join(MODELS_DIR, "PRODUCTION_eesob_48class_best.pt")),
    "faults": YOLO(os.path.join(MODELS_DIR, "PRODUCTION_pcb_faults_best.pt")),
    "missing": YOLO(os.path.join(MODELS_DIR, "circuitpulse_m2_Component-Detection-Arduino-UNO-1_best.pt")),
}
print(f"[INFO] Loaded {len(models)} models into memory.")

active_mode = "components"
detection_history = []


@app.route("/api/detect", methods=["POST"])
def detect_image():
    global detection_history

    if "image" in request.files:
        payload = request.files["image"].read()
        buf = np.frombuffer(payload, np.uint8)
        frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    elif request.json and "image_base64" in request.json:
        payload = base64.b64decode(request.json["image_base64"])
        buf = np.frombuffer(payload, np.uint8)
        frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    else:
        return jsonify({"error": "No image provided"}), 400

    if frame is None:
        return jsonify({"error": "Could not decode image"}), 400

    model = models[active_mode]
    results = model.predict(frame, conf=0.50, verbose=False)

    detections = []
    for box in results[0].boxes:
        detections.append({
            "class": results[0].names[int(box.cls)],
            "confidence": round(float(box.conf), 3),
            "bbox": {
                "x1": int(box.xyxy[0][0]),
                "y1": int(box.xyxy[0][1]),
                "x2": int(box.xyxy[0][2]),
                "y2": int(box.xyxy[0][3]),
            },
        })

    annotated = results[0].plot()
    _, enc_buf = cv2.imencode(".jpg", annotated)
    encoded_b64 = base64.b64encode(enc_buf).decode("utf-8")

    entry = {
        "id": len(detection_history) + 1,
        "timestamp": datetime.now().isoformat(),
        "mode": active_mode,
        "num_detections": len(detections),
        "detections": detections,
    }
    detection_history.append(entry)

    return jsonify({
        "success": True,
        "mode": active_mode,
        "num_detections": len(detections),
        "detections": detections,
        "annotated_image": f"data:image/jpeg;base64,{encoded_b64}",
    })


@app.route("/api/stream")
def mjpeg_stream():
    def frame_generator():
        cap = cv2.VideoCapture(CAMERA_URL)
        while True:
            success, frame = cap.read()
            if not success:
                cap.release()
                cap = cv2.VideoCapture(CAMERA_URL)
                continue

            results = models[active_mode].predict(frame, conf=0.50, verbose=False)
            annotated = results[0].plot()
            _, buf = cv2.imencode(".jpg", annotated)
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" +
                   buf.tobytes() + b"\r\n")

    return Response(frame_generator(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/api/mode", methods=["POST"])
def set_active_mode():
    global active_mode
    mode = (request.json or {}).get("mode", "components")
    if mode in models:
        active_mode = mode
        return jsonify({"success": True, "active_mode": active_mode})
    return jsonify({"error": f"Unknown mode: {mode}"}), 400


@app.route("/api/history")
def get_history_records():
    return jsonify({"history": detection_history})


@app.route("/api/status")
def healthcheck():
    return jsonify({
        "status": "online",
        "active_mode": active_mode,
        "models_loaded": list(models.keys()),
        "camera_url": CAMERA_URL,
    })


if __name__ == "__main__":
    print(f"[INFO] Server starting on http://0.0.0.0:{PORT} (mode: {active_mode})")
    app.run(host="0.0.0.0", port=PORT, debug=False)
