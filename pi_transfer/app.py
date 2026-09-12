import os
import time
import base64
import threading
import urllib.request
from datetime import datetime

import cv2
import numpy as np
from flask import Flask, request, jsonify, Response, send_file
try:
    from flask_cors import CORS
except ImportError:
    def CORS(app):
        pass
from ultralytics import YOLO

from circuit import CircuitEngine
from tracker import BoxSmoother
from resistor import ResistorDecoder

app = Flask(__name__)
CORS(app)

base_dir = os.path.dirname(os.path.abspath(__file__))
models_dir = os.path.join(base_dir, "models")
camera_url = "http://192.0.0.4:8080/video"
port = 5000

# Tuned baseline confidence thresholds
CONF_DEFAULT = 0.35
CONF_RESISTOR = 0.32
CONF_BOARD = 0.50
CONF_WIRE = 0.35
IMG_SIZE = 416
MAX_DETECTIONS = 35
FRAME_WIDTH = 640
MIN_BOX_AREA = 35
MAX_BOX_RATIO = 0.95
IOU_THRESHOLD = 0.30

# Strict whitelist: ONLY actual circuit components, zero tablecloth noise
ALLOWED_CLASSES = {
    "arduino_uno", "arduino_nano", "arduino_mega", "esp32", "breadboard",
    "resistor", "wire", "led"
}

def resolve_model(name, fallback):
    p1 = os.path.join(models_dir, name)
    if os.path.exists(p1):
        return p1
    return os.path.join(models_dir, fallback)

dual_model_paths = {
    "main": resolve_model("base.pt", "PRODUCTION_eesob_48class_best.pt"),
    "passives": resolve_model("passives.pt", "circuitpulse_m1_Resistor-Detection--5_best.pt"),
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


def trigger_phone_autofocus():
    try:
        base_url = camera_url.rsplit('/', 1)[0]
        req = urllib.request.Request(f"{base_url}/focus", headers={'User-Agent': 'Mozilla/5.0'})
        urllib.request.urlopen(req, timeout=1.0)
    except Exception:
        pass


def load_dual_models():
    global model_main, model_passives, active_mode
    active_mode = "all"

    import torch
    try:
        torch.set_num_threads(4)
    except Exception:
        pass

    def _pick(ncnn_name, pt_key):
        pt_path = dual_model_paths[pt_key]
        if os.path.exists(pt_path):
            print(f"  Using PyTorch: {pt_path}")
            return YOLO(pt_path)
        ncnn_path = os.path.join(models_dir, ncnn_name)
        if os.path.isdir(ncnn_path):
            print(f"  Using NCNN: {ncnn_name}")
            return YOLO(ncnn_path, task="detect")
        return YOLO(pt_path)

    print("Loading models...")
    model_main = _pick("base_ncnn_model", "main")
    model_passives = _pick("passives_ncnn_model", "passives")
    print("Ready.")


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

    # Deduplicate non-wires with standard NMS
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

    # Merge duplicate / fragmented ends of the same jumper wire
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

            # Merge if overlapping or adjacent segments of the same jumper wire
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
    # Real resistors have vibrant color bands and body tint (saturation > 32)
    # Molded black/dark gray DuPont plastic jumper tips have near-zero saturation (< 22) and low value (< 115)
    if sat < 22 and val < 115:
        return True
    return False


def filter_detections(boxes, frame_w, frame_h, full_frame=None):
    board_classes = {"arduino_uno", "arduino_nano", "arduino_mega", "esp32", "breadboard"}
    clean_boxes = []

    # Find boards to define legitimate circuit workspace and suppress tablecloth noise
    boards = [b for b in boxes if b["class"].lower() in board_classes and b["confidence"] >= CONF_BOARD]
    has_boards = len(boards) > 0
    if has_boards:
        bx1 = min(b["bbox"]["x1"] for b in boards) - 150
        by1 = min(b["bbox"]["y1"] for b in boards) - 150
        bx2 = max(b["bbox"]["x2"] for b in boards) + 150
        by2 = max(b["bbox"]["y2"] for b in boards) + 150

    for b in boxes:
        cls_name = b["class"].lower().replace("-", "_").replace(" ", "_")

        # Suppress any class outside ALLOWED_CLASSES (drops pile, support_pile, gaz, etc.)
        if cls_name not in ALLOWED_CLASSES and "arduino" not in cls_name:
            continue

        if "pin" in cls_name and "hole" in cls_name:
            continue

        bbox = b["bbox"]
        bw = bbox["x2"] - bbox["x1"]
        bh = bbox["y2"] - bbox["y1"]
        area = bw * bh
        frame_area = frame_w * frame_h

        if area < MIN_BOX_AREA or area > (frame_area * MAX_BOX_RATIO):
            continue

        # Suppress tablecloth background noise if outside circuit workspace
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
            # A wire is elongated, not a square tablecloth patch
            aspect = min(bw, bh) / float(max(bw, bh) + 1e-5)
            if aspect > 0.88 and min(bw, bh) > 30:
                continue

        if cls_name == "resistor":
            if b["confidence"] < CONF_RESISTOR:
                continue
            # Check if this resistor box is actually a black DuPont jumper wire tip
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


def draw_hud(frame, detections, verification_report, fps_val):
    annotated = frame.copy()

    color_map = {
        "wire": (0, 235, 140),
        "resistor": (0, 165, 255),
        "arduino_uno": (255, 190, 0),
        "arduino_nano": (255, 190, 0),
        "arduino_mega": (255, 190, 0),
        "esp32": (255, 120, 0),
        "breadboard": (180, 180, 180),
        "led": (0, 255, 255),
        "capacitor": (255, 0, 180),
    }

    for d in detections:
        cls_name = d["class"]
        bbox = d["bbox"]
        conf = d["confidence"]
        color = color_map.get(cls_name.lower(), (0, 220, 100))

        cv2.rectangle(annotated, (bbox["x1"], bbox["y1"]), (bbox["x2"], bbox["y2"]), color, 2)

        if cls_name.lower() == "resistor":
            if d.get("resistance"):
                bands = d.get("bands_str", "")
                if bands:
                    label = f"resistor {d['resistance']} [{bands}]"
                else:
                    label = f"resistor {d['resistance']}"
            else:
                label = f"resistor {conf:.0%}"
        else:
            label = f"{cls_name} {conf:.0%}"

        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        cv2.rectangle(annotated, (bbox["x1"], max(0, bbox["y1"] - th - 6)),
                      (bbox["x1"] + tw + 4, bbox["y1"]), color, -1)
        cv2.putText(annotated, label, (bbox["x1"] + 2, max(th, bbox["y1"] - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)

    h, w = annotated.shape[:2]
    errors = verification_report.get("errors", [])
    mcu_label = verification_report.get("mcu_info", "")
    circuit_title = verification_report.get("circuit_name", "Auto-Scanning")

    if errors:
        primary_msg = errors[0].get("message", "FAULT DETECTED")
        primary_remedy = errors[0].get("remedy", "")
        box_bottom = 86 if primary_remedy else 64
        cv2.rectangle(annotated, (10, 34), (min(w - 10, 630), box_bottom), (20, 20, 140), -1)
        cv2.rectangle(annotated, (10, 34), (min(w - 10, 630), box_bottom), (60, 60, 240), 2)
        disp_fault = f"! FAULT: {primary_msg}"
        if len(disp_fault) > 54:
            disp_fault = disp_fault[:51] + "..."
        cv2.putText(annotated, disp_fault,
                    (20, 54), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (255, 255, 255), 1, cv2.LINE_AA)
        if primary_remedy:
            disp_sol = f"> SOLUTION: {primary_remedy}"
            if len(disp_sol) > 54:
                disp_sol = disp_sol[:51] + "..."
            cv2.putText(annotated, disp_sol,
                        (20, 76), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (120, 255, 160), 1, cv2.LINE_AA)
        status_label = "CIRCUIT: FAULT DETECTED"
        status_color = (0, 0, 255)
    else:
        cv2.rectangle(annotated, (10, 34), (min(w - 10, 630), 82), (20, 140, 40), -1)
        cv2.rectangle(annotated, (10, 34), (min(w - 10, 630), 82), (60, 230, 80), 2)
        mcu_txt = f" [{mcu_label}]" if mcu_label else ""
        cv2.putText(annotated, f"CIRCUIT: ALL OK -- {circuit_title}{mcu_txt}",
                    (20, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.46, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(annotated, "> All connections and components verified working.",
                    (20, 74), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (180, 255, 200), 1, cv2.LINE_AA)
        status_label = "CIRCUIT: ALL OK"
        status_color = (0, 235, 100)

    cv2.putText(annotated, f"{fps_val} FPS | {status_label} | {circuit_title}",
                (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.50, status_color, 2, cv2.LINE_AA)

    return annotated


def capture_loop():
    global latest_frame, camera_connected
    print(f"Connecting to: {camera_url}")

    while True:
        try:
            cap = cv2.VideoCapture(camera_url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if not cap.isOpened():
                camera_connected = False
                time.sleep(1.5)
                continue

            camera_connected = True
            print("Connected.")

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


last_server_tts_time = 0
last_server_tts_text = ""


def speak_on_pi(text):
    global last_server_tts_time, last_server_tts_text
    now = time.time()
    if not text or (text == last_server_tts_text and (now - last_server_tts_time) < 5.0):
        return
    last_server_tts_time = now
    last_server_tts_text = text

    def _worker():
        try:
            import shutil
            import subprocess
            if shutil.which("espeak-ng"):
                subprocess.run(["espeak-ng", "-ven+f3", "-s", "150", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
            elif shutil.which("espeak"):
                subprocess.run(["espeak", "-ven+f3", "-s", "150", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
            elif shutil.which("spd-say"):
                subprocess.run(["spd-say", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
        except Exception:
            pass

    threading.Thread(target=_worker, daemon=True).start()


def inference_loop():
    global latest_detections, latest_timestamp
    global infer_fps, infer_ms, latest_verification_report
    global last_resistor_spoken, last_resistor_speak_time

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

            if active_mode == "all" and model_main and model_passives:
                # 1. Run passives (wire, resistor, breadboard)
                d_pass = run_inference(model_passives, frame)
                # 2. Run main model (strictly filtered to arduino & led)
                d_main_raw = run_inference(model_main, frame)
                d_main = [b for b in d_main_raw if b["class"].lower() in {"arduino_uno", "arduino_nano", "arduino_mega", "esp32", "breadboard", "led"}]

                # 3. Merge and deduplicate
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
                    # Macro inspection: decode when brought close (crop width >= 25px)
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

                            now_s = time.time()
                            res_key = f"{info['ohms']}_{bands_cap}"
                            if res_key != last_resistor_spoken or (now_s - last_resistor_speak_time > 15.0):
                                last_resistor_spoken = res_key
                                last_resistor_speak_time = now_s
                                speak_on_pi(f"Resistor identified: {info['raw_value']}. Colour bands: {bands_cap.replace('-', ', ')}.")

            smoothed_detections = box_smoother.update(raw_detections)
            for sm in smoothed_detections:
                if sm["class"].lower() == "resistor" and "resistance" not in sm:
                    for raw in raw_detections:
                        if raw["class"].lower() == "resistor" and "resistance" in raw:
                            if get_iou(sm["bbox"], raw["bbox"]) > 0.35:
                                sm["resistance"] = raw["resistance"]
                                sm["raw_value"] = raw["raw_value"]
                                sm["ohms"] = raw["ohms"]
                                sm["bands"] = raw.get("bands", [])
                                sm["bands_str"] = raw.get("bands_str", "")
                                break

            report = circuit_engine.verify(smoothed_detections, frame_width=w, frame_height=h)

            if report.get("status") == "PASS" and not report.get("errors"):
                if not report.get("tts"):
                    report["tts"] = f"Circuit is all OK. {report.get('circuit_name')} is verified working."

            if report.get("tts"):
                speak_on_pi(report["tts"])

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
            print(f"Error: {e}")
            time.sleep(0.05)


def get_standby_frame():
    canvas = np.zeros((540, FRAME_WIDTH, 3), dtype=np.uint8)
    canvas[:] = (26, 22, 18)
    cv2.putText(canvas, "CAMERA DISCONNECTED", (int(FRAME_WIDTH / 2 - 170), 230),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 100, 255), 2, cv2.LINE_AA)
    cv2.putText(canvas, f"Target: {camera_url}", (int(FRAME_WIDTH / 2 - 150), 270),
                cv2.FONT_HERSHEY_SIMPLEX, 0.50, (160, 160, 160), 1, cv2.LINE_AA)
    cv2.putText(canvas, "Keep phone screen active in IP Webcam", (int(FRAME_WIDTH / 2 - 180), 310),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (120, 120, 120), 1, cv2.LINE_AA)
    return canvas


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
                dets = list(latest_detections)
                report = dict(latest_verification_report)
                connected = camera_connected

            if connected and frame is not None:
                frames_sent += 1
                now = time.time()
                if now - last_time >= 1.0:
                    display_fps = frames_sent
                    frames_sent = 0
                    last_time = now

                annotated = draw_hud(frame, dets, report, display_fps)
                _, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n\r\n" +
                       buf.tobytes() + b"\r\n")
                elapsed = time.time() - t0
                time.sleep(max(0.001, 0.033 - elapsed))
            else:
                standby = get_standby_frame()
                _, buf = cv2.imencode(".jpg", standby, [cv2.IMWRITE_JPEG_QUALITY, 50])
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n\r\n" +
                       buf.tobytes() + b"\r\n")
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
    with frame_lock:
        dets = list(latest_detections)
    detected_by_class = {}
    for d in dets:
        cls = d["class"].lower().replace("-", "_").replace(" ", "_")
        detected_by_class.setdefault(cls, []).append(d)
    board_kws = ["arduino", "esp32", "esp8266", "breadboard"]
    trusted_by_class = {}
    for cls, items in detected_by_class.items():
        if any(kw in cls for kw in board_kws):
            trusted = [it for it in items if it.get("confidence", 0) >= BOARD_MIN_CONF]
        else:
            trusted = list(items)
        if trusted:
            trusted_by_class[cls] = trusted

    detected_id, detected_name, mcu_name = circuit_engine.auto_detect_circuit(trusted_by_class, detected_by_class)

    return jsonify({
        "circuits": circuit_engine.list_circuits(),
        "auto_detected": {
            "id": detected_id,
            "name": detected_name,
            "mcu": mcu_name
        }
    })


@app.route("/api/mode", methods=["POST"])
def set_mode():
    return jsonify({"status": "ok", "mode": active_mode})


@app.route("/api/trigger-autofocus", methods=["POST"])
def api_autofocus():
    trigger_phone_autofocus()
    return jsonify({"status": "ok", "action": "focus_triggered"})


@app.route("/")
def index():
    html_path = os.path.join(base_dir, "index.html")
    if os.path.exists(html_path):
        return send_file(html_path)
    return "CircuitPulse Vision Server Active"


def main():
    load_dual_models()
    threading.Thread(target=capture_loop, daemon=True).start()
    threading.Thread(target=inference_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=port, threaded=True)


if __name__ == "__main__":
    main()
