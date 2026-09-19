import os
import sys
import time
import base64
import threading
import urllib.request
from datetime import datetime

import cv2
import numpy as np
from flask import Flask, request, jsonify, Response, send_file, send_from_directory
try:
    from flask_cors import CORS
except ImportError:
    def CORS(app):
        pass
from ultralytics import YOLO

base_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.dirname(base_dir)
sys.path.insert(0, os.path.join(repo_root, "engine"))
sys.path.insert(0, os.path.join(repo_root, "vision"))
sys.path.insert(0, os.path.join(repo_root, "pi_transfer"))

from circuit import CircuitEngine
from tracker import BoxSmoother
from resistor import ResistorDecoder

ar_dir = os.path.join(repo_root, "ar")
models_dir = os.path.join(repo_root, "pi_transfer", "models")
camera_url = "http://192.0.0.4:8080/video"
port = 5000

app = Flask(__name__, static_folder=ar_dir)
CORS(app)

CONF_DEFAULT = 0.35
CONF_RESISTOR = 0.32
CONF_BOARD = 0.50
CONF_WIRE = 0.35
IMG_SIZE = 416
MAX_DETECTIONS = 40
FRAME_WIDTH = 640
MIN_BOX_AREA = 35
MAX_BOX_RATIO = 0.95
IOU_THRESHOLD = 0.30

ALLOWED_CLASSES = {
    "arduino_uno", "arduino_nano", "arduino_mega", "esp32", "breadboard",
    "resistor", "wire", "led"
}

def resolve_model(name):
    p = os.path.join(models_dir, name)
    if os.path.exists(p):
        return p
    return os.path.join(repo_root, "vision", "models", name)

dual_model_paths = {
    "main": resolve_model("base.pt"),
    "passives": resolve_model("passives.pt"),
}

active_mode = "all"
model_main = None
model_passives = None

box_smoother = BoxSmoother(alpha=0.65, iou_thresh=0.38, max_missing=2)
resistor_decoder = ResistorDecoder()
circuit_engine = CircuitEngine()

latest_verification_report = {
    "status": "PASS",
    "circuit_name": "Scanning for circuit...",
    "circuit_id": "none",
    "mcu_info": "",
    "errors": [],
    "warnings": []
}

latest_frame = None
latest_detections = []
latest_timestamp = ""
frame_lock = threading.Lock()

camera_connected = False
infer_fps = 0
infer_ms = 0
last_resistor_spoken = ""
last_resistor_speak_time = 0


def load_dual_models():
    global model_main, model_passives
    import torch
    try:
        torch.set_num_threads(4)
    except Exception:
        pass

    def _pick(ncnn_name, pt_key):
        pt_path = dual_model_paths[pt_key]
        if os.path.exists(pt_path):
            return YOLO(pt_path)
        ncnn_path = os.path.join(models_dir, ncnn_name)
        if os.path.isdir(ncnn_path):
            return YOLO(ncnn_path, task="detect")
        return YOLO(pt_path)

    print("Loading backend vision models...")
    model_main = _pick("base_ncnn_model", "main")
    model_passives = _pick("passives_ncnn_model", "passives")
    print("Backend ready.")


def get_iou(b1, b2):
    x1 = max(b1["x1"], b2["x1"])
    y1 = max(b1["y1"], b2["y1"])
    x2 = min(b1["x2"], b2["x2"])
    y2 = min(b1["y2"], b2["y2"])
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    area1 = (b1["x2"] - b1["x1"]) * (b1["y2"] - b1["y1"])
    area2 = (b2["x2"] - b2["x1"]) * (b2["y2"] - b2["y1"])
    union = area1 + area2 - intersection
    return intersection / union if union > 0 else 0.0


def deduplicate_and_merge_wires(boxes):
    if len(boxes) <= 1:
        return boxes

    non_wires = [b for b in boxes if b["class"] != "wire"]
    wires = [b for b in boxes if b["class"] == "wire"]

    sorted_non_wires = sorted(non_wires, key=lambda b: b["confidence"], reverse=True)
    kept_non_wires = []
    for box in sorted_non_wires:
        overlap = False
        for existing in kept_non_wires:
            if existing["class"] == box["class"] and get_iou(box["bbox"], existing["bbox"]) > IOU_THRESHOLD:
                overlap = True
                break
        if not overlap:
            kept_non_wires.append(box)

    merged_wires = []
    used_wire_indices = set()

    for i in range(len(wires)):
        if i in used_wire_indices:
            continue
        w1 = wires[i]["bbox"]
        cur_box = dict(w1)
        cur_conf = wires[i]["confidence"]

        for j in range(i + 1, len(wires)):
            if j in used_wire_indices:
                continue
            w2 = wires[j]["bbox"]

            iou = get_iou(cur_box, w2)
            dist_x = min(abs(cur_box["x1"] - w2["x2"]), abs(cur_box["x2"] - w2["x1"]))
            dist_y = min(abs(cur_box["y1"] - w2["y2"]), abs(cur_box["y2"] - w2["y1"]))

            if iou > 0.15 or (dist_x < 35 and dist_y < 35):
                cur_box["x1"] = min(cur_box["x1"], w2["x1"])
                cur_box["y1"] = min(cur_box["y1"], w2["y1"])
                cur_box["x2"] = max(cur_box["x2"], w2["x2"])
                cur_box["y2"] = max(cur_box["y2"], w2["y2"])
                cur_conf = max(cur_conf, wires[j]["confidence"])
                used_wire_indices.add(j)

        used_wire_indices.add(i)
        merged_wires.append({
            "class": "wire",
            "confidence": cur_conf,
            "bbox": cur_box
        })

    return kept_non_wires + merged_wires


def is_black_dupont_connector(crop):
    if crop is None or crop.shape[0] < 4 or crop.shape[1] < 4:
        return False
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    sat = np.mean(hsv[:, :, 1])
    val = np.mean(hsv[:, :, 2])
    if sat < 22 and val < 115:
        return True
    return False


def filter_detections(boxes, frame_w, frame_h, full_frame=None):
    board_classes = {"arduino_uno", "arduino_nano", "arduino_mega", "esp32", "breadboard"}
    clean_boxes = []

    boards = [b for b in boxes if b["class"].lower() in board_classes and b["confidence"] >= CONF_BOARD]
    has_boards = len(boards) > 0
    if has_boards:
        bx1 = min(b["bbox"]["x1"] for b in boards) - 150
        by1 = min(b["bbox"]["y1"] for b in boards) - 150
        bx2 = max(b["bbox"]["x2"] for b in boards) + 150
        by2 = max(b["bbox"]["y2"] for b in boards) + 150

    for b in boxes:
        cls_name = b["class"].lower().replace("-", "_").replace(" ", "_")

        if cls_name not in ALLOWED_CLASSES and "arduino" not in cls_name:
            continue

        bbox = b["bbox"]
        bw = bbox["x2"] - bbox["x1"]
        bh = bbox["y2"] - bbox["y1"]
        area = bw * bh
        frame_area = frame_w * frame_h

        if area < MIN_BOX_AREA or area > (frame_area * MAX_BOX_RATIO):
            continue

        if has_boards and cls_name not in board_classes:
            outside = (bbox["x2"] < bx1 or bbox["x1"] > bx2 or bbox["y2"] < by1 or bbox["y1"] > by2)
            if outside and b["confidence"] < 0.45:
                continue

        if cls_name in board_classes:
            if b["confidence"] < CONF_BOARD:
                continue

        if cls_name == "wire":
            if b["confidence"] < CONF_WIRE:
                continue

        if cls_name == "resistor":
            if b["confidence"] < CONF_RESISTOR:
                continue
            if full_frame is not None:
                rx1 = max(0, bbox["x1"])
                ry1 = max(0, bbox["y1"])
                rx2 = min(frame_w, bbox["x2"])
                ry2 = min(frame_h, bbox["y2"])
                if rx2 > rx1 and ry2 > ry1:
                    crop = full_frame[ry1:ry2, rx1:rx2]
                    if is_black_dupont_connector(crop):
                        continue

        clean_boxes.append(b)

    return clean_boxes


def run_inference(model, frame):
    results = model.predict(
        frame,
        conf=0.28,
        imgsz=IMG_SIZE,
        max_det=MAX_DETECTIONS,
        verbose=False
    )
    parsed_boxes = []
    for box in results[0].boxes:
        label = results[0].names[int(box.cls)]
        conf = round(float(box.conf), 3)
        coords = box.xyxy[0]
        bbox = {
            "x1": int(coords[0]),
            "y1": int(coords[1]),
            "x2": int(coords[2]),
            "y2": int(coords[3]),
        }
        parsed_boxes.append({
            "class": label,
            "confidence": conf,
            "bbox": bbox,
        })
    return parsed_boxes


def capture_loop():
    global latest_frame, camera_connected
    while True:
        try:
            cap = cv2.VideoCapture(camera_url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if not cap.isOpened():
                camera_connected = False
                time.sleep(1.5)
                continue

            camera_connected = True
            while True:
                ret, frame = cap.read()
                if not ret or frame is None:
                    camera_connected = False
                    with frame_lock:
                        latest_frame = None
                    break

                h, w = frame.shape[:2]
                if w > FRAME_WIDTH:
                    scale = FRAME_WIDTH / float(w)
                    frame = cv2.resize(
                        frame,
                        (FRAME_WIDTH, int(h * scale)),
                        interpolation=cv2.INTER_LINEAR
                    )

                with frame_lock:
                    latest_frame = frame

            cap.release()
            time.sleep(0.5)
        except Exception:
            camera_connected = False
            with frame_lock:
                latest_frame = None
            time.sleep(1.5)


def inference_loop():
    global latest_detections, latest_timestamp
    global infer_fps, infer_ms, latest_verification_report

    prev_frame_id = None
    infer_count = 0
    last_fps_time = time.time()

    while True:
        with frame_lock:
            frame = latest_frame
            current_id = id(frame)

        if frame is None or current_id == prev_frame_id:
            time.sleep(0.01)
            continue

        prev_frame_id = current_id

        try:
            t0 = time.time()
            raw_detections = []
            h, w = frame.shape[:2]

            if model_main and model_passives:
                d_pass = run_inference(model_passives, frame)
                d_main_raw = run_inference(model_main, frame)
                d_main = [b for b in d_main_raw if b["class"].lower() in {"arduino_uno", "arduino_nano", "arduino_mega", "esp32", "breadboard", "led"}]
                merged = deduplicate_and_merge_wires(d_pass + d_main)
                raw_detections = filter_detections(merged, w, h, full_frame=frame)
            else:
                time.sleep(0.05)
                continue

            for d in raw_detections:
                if d["class"].lower() == "resistor":
                    bbox = d["bbox"]
                    rx1 = max(0, bbox["x1"])
                    ry1 = max(0, bbox["y1"])
                    rx2 = min(w, bbox["x2"])
                    ry2 = min(h, bbox["y2"])
                    if (rx2 - rx1) >= 25 and (ry2 - ry1) >= 10:
                        crop = frame[ry1:ry2, rx1:rx2]
                        info = resistor_decoder.decode(crop)
                        if info:
                            d["resistance"] = info["formatted"]
                            d["raw_value"] = info["raw_value"]
                            d["ohms"] = info["ohms"]
                            d["bands"] = info.get("bands", [])
                            bands_cap = "-".join([b.capitalize() for b in info.get("bands", [])])
                            d["bands_str"] = bands_cap

            smoothed_detections = box_smoother.update(raw_detections)
            report = circuit_engine.verify(smoothed_detections, frame_width=w, frame_height=h)

            with frame_lock:
                latest_verification_report = report
                latest_detections = smoothed_detections
                latest_timestamp = datetime.now().isoformat()

            infer_count += 1
            infer_ms = round((time.time() - t0) * 1000, 1)
            now = time.time()
            if now - last_fps_time >= 1.0:
                infer_fps = infer_count
                infer_count = 0
                last_fps_time = now

        except Exception as e:
            print(f"Inference error: {e}")
            time.sleep(0.05)


@app.route("/")
def index():
    index_path = os.path.join(ar_dir, "index.html")
    if os.path.exists(index_path):
        return send_file(index_path)
    return "CircuitPulse Backend Active"


@app.route("/<path:filename>")
def serve_ar_assets(filename):
    return send_from_directory(ar_dir, filename)


@app.route("/api/stream")
def stream():
    def generate():
        last_time = time.time()
        frames_sent = 0
        display_fps = 30

        while True:
            t0 = time.time()
            with frame_lock:
                frame = None if latest_frame is None else latest_frame.copy()
                connected = camera_connected

            if connected and frame is not None:
                frames_sent += 1
                now = time.time()
                if now - last_time >= 1.0:
                    display_fps = frames_sent
                    frames_sent = 0
                    last_time = now

                _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n\r\n" +
                       buf.tobytes() + b"\r\n")
                elapsed = time.time() - t0
                time.sleep(max(0.001, 0.033 - elapsed))
            else:
                time.sleep(0.5)

    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/api/detections")
def get_detections():
    with frame_lock:
        return jsonify({
            "detections": latest_detections,
            "timestamp": latest_timestamp,
            "camera_connected": camera_connected,
            "active_mode": active_mode,
            "infer_fps": infer_fps,
            "infer_ms": infer_ms,
            "verification": latest_verification_report
        })


@app.route("/api/verification")
def get_verification():
    with frame_lock:
        return jsonify(latest_verification_report)


@app.route("/api/circuits")
def get_circuits():
    return jsonify({
        "circuits": circuit_engine.list_circuits()
    })


@app.route("/api/trigger-autofocus", methods=["POST"])
def api_autofocus():
    try:
        base_url = camera_url.rsplit('/', 1)[0]
        req = urllib.request.Request(f"{base_url}/focus", headers={'User-Agent': 'Mozilla/5.0'})
        urllib.request.urlopen(req, timeout=1.0)
    except Exception:
        pass
    return jsonify({"status": "ok", "action": "focus_triggered"})

@app.route("/api/scan-frame", methods=["POST"])
def scan_frame():
    file = request.files.get("frame")
    if not file:
        return jsonify({"error": "no frame uploaded"}), 400

    data = file.read()
    nparr = np.frombuffer(data, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if frame is None:
        return jsonify({"error": "could not decode image"}), 400

    if not (model_main and model_passives):
        return jsonify({"error": "models not loaded yet"}), 503

    h, w = frame.shape[:2]
    d_pass = run_inference(model_passives, frame)
    d_main_raw = run_inference(model_main, frame)
    d_main = [b for b in d_main_raw if b["class"].lower() in {"arduino_uno", "arduino_nano", "arduino_mega", "esp32", "breadboard", "led"}]
    merged = deduplicate_and_merge_wires(d_pass + d_main)
    detections = filter_detections(merged, w, h, full_frame=frame)

    for d in detections:
        if d["class"].lower() == "resistor":
            bbox = d["bbox"]
            rx1 = max(0, bbox["x1"]); ry1 = max(0, bbox["y1"])
            rx2 = min(w, bbox["x2"]); ry2 = min(h, bbox["y2"])
            if (rx2 - rx1) >= 25 and (ry2 - ry1) >= 10:
                crop = frame[ry1:ry2, rx1:rx2]
                info = resistor_decoder.decode(crop)
                if info:
                    d["resistance"] = info["formatted"]

    report = circuit_engine.verify(detections, frame_width=w, frame_height=h)

    return jsonify({"success": True, "detections": detections, "verification": report})

def main():
    load_dual_models()
    threading.Thread(target=capture_loop, daemon=True).start()
    threading.Thread(target=inference_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=port, threaded=True)


if __name__ == "__main__":
    main()
