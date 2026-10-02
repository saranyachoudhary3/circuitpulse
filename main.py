import os
import cv2
import numpy as np
import time
import threading
import sys
import argparse
from pathlib import Path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import datetime
from flask import Flask, jsonify, Response, request, send_file, send_from_directory
try:
    from flask_socketio import SocketIO, join_room
except ImportError:  # The REST session API remains available for minimal installs.
    SocketIO = None
    join_room = None

from camera import CameraSourceError, VideoStreamer, normalize_camera_source
from detectors.tracker import Tracker
from detectors.resistor import ResistorDecoder
from detectors.wires import WireTracer
from detectors.zoom import AutoZoom
from detectors.memory import WireMemory
from logic.solver import CircuitSolver
from logic.netlist import NetlistError, NetlistVerifier
from logic.catalog import CatalogError, ComponentCatalog, PresetCatalog
from logic.session import SessionError, SessionManager
from logic.audit import SessionAuditLog, AuditError
from logic.bridge import VisionGraphBridge
from logic.firmware import analyze_firmware, verify_firmware_against_preset
from logic.eda import EdaImportError, import_kicad_legacy_netlist, import_spice_netlist
from logic.instruments import InstrumentRegistry
from logic.benchmark import BenchmarkError, replay_suite
from logic.simulation import run_operating_point
from logic.digital_twin import DigitalTwinEngine
from logic.readiness import ReadinessError, automatic_verification_readiness
from logic.circuit_ir import CircuitIRError
from logic.logic_engine import CircuitLogicEngine
from logic.repair_planner import RepairPlanner
from vision.calibration import CalibrationError, CalibrationMat
from logic.snapshot import SnapshotManager
from logic.gpio import GPIOController
from intelligence.vlm import CircuitAnalyzer
from vision.runtime import choose_model
from vision.fiducials import ModuleFiducialDetector
from vision.evidence_contract import VisionEvidenceError, VisionEvidenceValidator

app = Flask(__name__)
# Same-origin WebSockets only.  The default demo binds to loopback; exposing it
# on a LAN requires an explicit command-line choice by the operator.
socketio = SocketIO(app, async_mode="threading") if SocketIO else None
port = 5000
web_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "web"))

model_master = None
model_backend = "unavailable"
model_selection_reason = "not loaded"
model_verified = False
model_artifact_id = None
box_smoother = Tracker(alpha=0.5, max_missing=3)
resistor_decoder = ResistorDecoder()
circuit_engine = CircuitSolver()
netlist_verifier = NetlistVerifier()
component_catalog = ComponentCatalog()
module_fiducials = ModuleFiducialDetector(component_catalog)
vision_evidence_validator = VisionEvidenceValidator(component_catalog)
preset_catalog = PresetCatalog()

def _broadcast_session_state(state):
    if socketio is not None:
        socketio.emit("session_state", state, to=f"session:{state['session_id']}")

session_audit_log = SessionAuditLog(Path(__file__).resolve().parent / "artifacts" / "audit")
session_manager = SessionManager(preset_catalog, _broadcast_session_state, session_audit_log)
vision_graph_bridge = VisionGraphBridge()
calibration_mat = CalibrationMat()
instrument_registry = InstrumentRegistry()
digital_twin_engine = DigitalTwinEngine(component_catalog)
logic_engine = CircuitLogicEngine()
repair_planner = RepairPlanner()
ptz_tracker = AutoZoom(alpha=0.1, margin=0.3)
endpoint_tracker = WireMemory(max_missing=15) # Remember endpoints for 15 frames if occluded
snapshot_engine = SnapshotManager()
hardware_controller = GPIOController()
circuit_analyzer = CircuitAnalyzer()



latest_frame = None
latest_detections = []
latest_verification_report = {}
latest_timestamp = ""
camera_connected = False
infer_fps = 0
infer_ms = 0
frame_lock = threading.Lock()
latest_vlm_analysis = None

# Global dynamic dimensions
FRAME_WIDTH = 1920
FRAME_HEIGHT = 1080

def load_models():
    global model_master, model_backend, model_selection_reason, model_verified, model_artifact_id
    from ultralytics import YOLO
    try:
        selection = choose_model(Path(__file__).resolve().parent)
        print(f"Loading {selection.backend} model: {selection.path} ({selection.reason})")
        model_master = YOLO(selection.path)
        model_backend = selection.backend
        model_selection_reason = selection.reason
        model_verified = selection.verified
        model_artifact_id = selection.artifact_id
    except Exception as e:
        print(f"Error loading model: {e}")
        model_backend = "unavailable"
        model_selection_reason = str(e)
        model_verified = False
        model_artifact_id = None

def run_inference(model, frame):
    # Run inference at 640x640 (what YOLO11s was trained on)
    results = model.predict(source=frame, imgsz=640, conf=0.25, verbose=False)
    detections = []
    if results and len(results) > 0 and results[0].boxes:
        for box in results[0].boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            cls_name = model.names[cls_id].lower()
            detections.append({
                "class": cls_name,
                "confidence": round(conf, 3),
                "bbox": {"x1": int(x1), "y1": int(y1), "x2": int(x2), "y2": int(y2)}
            })
    # Strict Deduplication for unique topological anchors (Breadboard, MCU)
    final_detections = []
    seen_unique = {}
    
    # Sort by confidence so we process highest confidence first
    detections.sort(key=lambda x: x["confidence"], reverse=True)
    
    mcu_classes = ['arduino_uno', 'arduino_nano', 'arduino_mega', 'esp32']
    
    for d in detections:
        cls = d["class"]
        
        # Determine the unique category constraint
        constraint_key = None
        if cls == 'breadboard':
            constraint_key = 'breadboard'
        elif cls in mcu_classes:
            constraint_key = 'mcu'
            
        if constraint_key:
            if constraint_key in seen_unique:
                continue # Skip lower confidence duplicate
            seen_unique[constraint_key] = True
            final_detections.append(d)
        else:
            final_detections.append(d)
            
    return final_detections

def inference_loop(streamer):
    global latest_detections, latest_timestamp, infer_fps, infer_ms, latest_verification_report, camera_connected, latest_frame, FRAME_WIDTH, FRAME_HEIGHT
    
    last_fps_time = time.time()
    infer_count = 0
    
    # Update dynamic frame dimensions based on streamer connection
    if streamer.actual_width > 0:
        FRAME_WIDTH = streamer.actual_width
        FRAME_HEIGHT = streamer.actual_height
        
    print(f"Inference Loop Started. Native Resolution: {FRAME_WIDTH}x{FRAME_HEIGHT}")
    
    while True:
        # A past frame is not live visual evidence.  It must cause the same
        # fail-safe reacquisition state as a hard capture failure.
        frame = streamer.read(max_age_seconds=1.0)
        if frame is None:
            camera_connected = False
            session_manager.set_camera_available(False)
            time.sleep(0.1)
            continue
            
        camera_connected = True
        session_manager.set_camera_available(True)
        
        try:
            t0 = time.time()
            if model_master is None:
                time.sleep(0.05)
                continue
                
            raw_detections = run_inference(model_master, frame)

            # Resistor Decoding
            for d in raw_detections:
                if d["class"].lower() == "resistor":
                    bbox = d["bbox"]
                    rx1, ry1 = max(0, bbox["x1"]), max(0, bbox["y1"])
                    rx2, ry2 = min(frame.shape[1], bbox["x2"]), min(frame.shape[0], bbox["y2"])
                    if (rx2 - rx1) >= 25 and (ry2 - ry1) >= 10:
                        crop = frame[ry1:ry2, rx1:rx2]
                        info = resistor_decoder.decode(crop)
                        if info:
                            d["resistance"] = info["formatted"]
                            d["bands_str"] = "-".join([b.capitalize() for b in info.get("bands", [])])

            # Apply temporal hysteresis
            smoothed_detections = box_smoother.update(raw_detections)
            
            # Disable PTZ Auto-Zoom to prevent video feed "collapsing"
            # Instead, just use the stable frame and smoothed detections directly
            final_detections = smoothed_detections
            
            for det in final_detections:
                if det["class"] == "wire":
                    ep1, ep2 = WireTracer.get_endpoints(frame, det["bbox"])
                    if ep1 and ep2:
                        det["endpoints"] = [list(ep1), list(ep2)]
            
            final_detections = endpoint_tracker.update(final_detections)
            report = circuit_engine.verify(final_detections, frame=frame, frame_width=FRAME_WIDTH, frame_height=FRAME_HEIGHT)
            
            # A camera-only report is an inspection result, not proof of
            # continuity. Do not label or archive it as electrically complete.
            if report.get("electrical_status") == "PASS":
                snapshot_engine.check_and_snap(report, frame)
            
            hardware_controller.update(report)

            # VLM Circuit Intelligence (runs in background, non-blocking)
            # Only trigger analysis if YOLO found AT LEAST one component, to prevent hallucinating on empty tables
            vlm_result = None
            if len(final_detections) > 0:
                vlm_result = circuit_analyzer.analyze(frame, final_detections)
            else:
                # If nothing is detected, clear the VLM result so it doesn't show old ghost circuits
                circuit_analyzer.latest_analysis = None

            if vlm_result:
                report["vlm_analysis"] = vlm_result

            with frame_lock:
                latest_frame = frame
                latest_verification_report = report
                latest_detections = final_detections
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
    return send_file(os.path.join(web_dir, "index.html"))

@app.route("/<path:filename>")
def serve_ar_assets(filename):
    return send_from_directory(web_dir, filename)

@app.route("/api/stream")
def stream():
    def generate():
        while True:
            if global_streamer is not None:
                frame = global_streamer.read(max_age_seconds=1.0)
                if frame is not None:
                    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n")
            time.sleep(0.033)
    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")

camera_base_url = None

@app.route("/api/focus", methods=["POST"])
def trigger_focus():
    if camera_base_url:
        import requests
        try:
            # IP Webcam's focus endpoint is /focus
            focus_url = camera_base_url.replace("/video", "/focus")
            requests.get(focus_url, timeout=2)
            return jsonify({"status": "success", "message": "Focus triggered"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)})
    return jsonify({"status": "error", "message": "Not an IP Camera"})

@app.route("/api/analyze", methods=["POST"])
def trigger_analyze():
    """Force an immediate VLM re-analysis."""
    circuit_analyzer.last_analysis_time = 0
    return jsonify({"status": "success", "message": "Analysis triggered"})

@app.route("/api/ask", methods=["POST"])
def ask_question():
    """Ask a question about the current circuit."""
    data = request.get_json() or {}
    question = data.get("question", "").strip()
    if not question:
        return jsonify({"status": "error", "message": "No question provided"})
    circuit_analyzer.ask_question(question)
    return jsonify({"status": "success", "message": "Question queued for next analysis"})

@app.route("/api/netlist/verify", methods=["POST"])
def verify_netlist():
    """Verify user-confirmed, probe-derived, or schematic-imported topology.

    The camera pipeline intentionally does not call this endpoint by itself:
    object detection cannot prove an electrical connection.  A client must
    supply the explicit netlist documented in ``logic/netlist.py``.
    """
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"status": "INVALID_INPUT", "message": "Send a JSON netlist."}), 400
    try:
        return jsonify(netlist_verifier.verify(payload))
    except NetlistError as error:
        return jsonify({"status": "INVALID_INPUT", "message": str(error)}), 400

@app.route("/api/circuit/analyze", methods=["POST"])
def analyze_typed_circuit():
    """Run deterministic typed-circuit, protocol, and operating-limit rules."""
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"status": "INVALID_INPUT", "message": "Send a typed circuit JSON object."}), 400
    try:
        return jsonify(logic_engine.analyze(payload))
    except CircuitIRError as error:
        return jsonify({"status": "INVALID_INPUT", "message": str(error)}), 400

@app.route("/api/presets/<preset_id>/repair-plan", methods=["POST"])
def create_repair_plan(preset_id):
    """Calculate ordered, minimal graph edits to reach one reviewed blueprint."""
    payload = request.get_json(silent=True) or {}
    try:
        preset = preset_catalog.get(preset_id)
        observed = payload.get("observed", [])
        if not isinstance(observed, list):
            raise ValueError("observed must be a list of connection objects.")
        return jsonify(repair_planner.plan(preset, observed, payload.get("findings")))
    except (CatalogError, ValueError) as error:
        return jsonify({"status": "INVALID_INPUT", "message": str(error)}), 400

@app.route("/api/sessions/<session_id>/repair-plan")
def session_repair_plan(session_id):
    """Return the ordered repair sequence for the authoritative live graph."""
    try:
        state = session_manager.get(session_id).state()
        deterministic = state.get("deterministic_verification", {})
        findings = []
        # Session findings already retain deterministic fault details and are
        # more current than a client-provided copy.
        for finding in state.get("findings", []):
            if finding.get("source") == "deterministic_verification":
                root = next((item for item in deterministic.get("root_causes", []) if item.get("code") == finding.get("code")), None)
                findings.append({**finding, "recommended_action": root.get("recommended_action") if root else None})
        plan = repair_planner.plan(session_manager.get(session_id).preset, state["graph"]["observed"], findings)
        return jsonify({"session_id": session_id, "graph_revision": state["graph_revision"], "status": state["status"],
                        "deterministic_status": deterministic.get("status"), **plan})
    except SessionError as error:
        return jsonify({"status": "NOT_FOUND", "message": str(error)}), 404

@app.route("/api/sessions/<session_id>/netlist/verify", methods=["POST"])
def verify_session_netlist(session_id):
    """Bind typed electrical evidence to one exact graph revision."""
    payload = request.get_json(silent=True) or {}
    try:
        report = logic_engine.analyze(payload.get("netlist"))
        state = session_manager.get(session_id).attach_deterministic_verification(
            report, payload.get("graph_revision"), payload.get("graph_fingerprint"),
            payload.get("terminal_nets"), payload.get("netlist"),
        )
        return jsonify(state)
    except (NetlistError, CircuitIRError, SessionError) as error:
        return jsonify({"status": "INVALID_INPUT", "message": str(error)}), 400

@app.route("/api/presets")
def list_presets():
    """List the reviewed circuit blueprints supported by the live debugger."""
    return jsonify({"schema_version": 1, "presets": preset_catalog.list_public()})

@app.route("/api/presets/identify", methods=["POST"])
def identify_presets():
    """Return candidates only; a user must select a blueprint before verification."""
    payload = request.get_json(silent=True) or {}
    components = payload.get("components", [])
    if not isinstance(components, list) or not all(isinstance(item, str) for item in components):
        return jsonify({"status": "INVALID_INPUT", "message": "components must be a list of component class names."}), 400
    return jsonify({"candidates": preset_catalog.identify(components)})

@app.route("/api/modules")
def list_modules():
    """Return reviewed, fiducial-backed modules; unknown modules are not trusted."""
    return jsonify({"schema_version": 1, "modules": component_catalog.list_public()})

@app.route("/api/modules/identify", methods=["POST"])
def identify_modules():
    """Identify reviewed modules from an uploaded calibration-frame image.

    This is intentionally separate from coarse YOLO classification: an unknown
    fiducial is never assumed to have a safe or known pin map.
    """
    uploaded = request.files.get("image")
    if uploaded is None:
        return jsonify({"status": "INVALID_INPUT", "message": "Upload an image form field."}), 400
    encoded = np.frombuffer(uploaded.read(), dtype=np.uint8)
    frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if frame is None:
        return jsonify({"status": "INVALID_INPUT", "message": "Uploaded image could not be decoded."}), 400
    return jsonify({"modules": module_fiducials.detect(frame)})

@app.route("/api/sessions", methods=["POST"])
def create_session():
    payload = request.get_json(silent=True) or {}
    try:
        state = session_manager.create(payload.get("preset_id", ""))
    except CatalogError as error:
        return jsonify({"status": "INVALID_INPUT", "message": str(error)}), 400
    return jsonify(state), 201

@app.route("/api/sessions/<session_id>/state")
def get_session_state(session_id):
    try:
        return jsonify(session_manager.get(session_id).state())
    except SessionError as error:
        return jsonify({"status": "NOT_FOUND", "message": str(error)}), 404

@app.route("/api/sessions/<session_id>/audit/verify")
def verify_session_audit(session_id):
    """Verify the append-only evidence sequence for one live session."""
    try:
        result = session_manager.verify_audit(session_id)
    except (SessionError, AuditError) as error:
        return jsonify({"status": "NOT_FOUND", "message": str(error)}), 404
    return jsonify(result), 200 if result["status"] == "PASS" else 503

@app.route("/api/sessions/<session_id>/observations", methods=["POST"])
def add_session_observations(session_id):
    """Accept calibrated vision candidates; the session fuses them over time."""
    payload = request.get_json(silent=True) or {}
    try:
        state = session_manager.get(session_id).observe(payload.get("connections"))
        return jsonify(state)
    except SessionError as error:
        return jsonify({"status": "INVALID_INPUT", "message": str(error)}), 400

@app.route("/api/sessions/<session_id>/vision-graph", methods=["POST"])
def add_calibrated_vision_graph(session_id):
    """Accept only provenance-bound automatic vision graph evidence."""
    payload = request.get_json(silent=True) or {}
    try:
        evidence = vision_evidence_validator.validate(payload, calibration_mat.state, model_verified, model_artifact_id)
        state = vision_graph_bridge.observe(session_manager.get(session_id), evidence["terminals"], evidence["wires"])
        return jsonify(state)
    except (SessionError, VisionEvidenceError, KeyError, TypeError, ValueError) as error:
        return jsonify({"status": "INVALID_INPUT", "message": str(error)}), 400

@app.route("/api/calibration", methods=["POST"])
def calibrate_mat():
    uploaded = request.files.get("image")
    if uploaded is None:
        return jsonify({"status": "INVALID_INPUT", "message": "Upload a calibration-mat image."}), 400
    frame = cv2.imdecode(np.frombuffer(uploaded.read(), dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        return jsonify({"status": "INVALID_INPUT", "message": "Uploaded image could not be decoded."}), 400
    try:
        return jsonify({"status": "PASS", "calibration": calibration_mat.calibrate(frame).as_dict()})
    except CalibrationError as error:
        return jsonify({"status": "INDETERMINATE", "message": str(error)}), 422

@app.route("/api/readiness")
def automatic_verification_readiness_api():
    """Report every hard gate before automatic live graph updates are enabled."""
    preset_id = request.args.get("preset_id")
    frame_size = (FRAME_WIDTH, FRAME_HEIGHT) if camera_connected else None
    try:
        return jsonify(automatic_verification_readiness(
            camera_connected=camera_connected, model_verified=model_verified, model_artifact_id=model_artifact_id,
            calibration_health=calibration_mat.health(frame_size), components=component_catalog,
            presets=preset_catalog, preset_id=preset_id,
        ))
    except CatalogError as error:
        return jsonify({"status": "INVALID_INPUT", "message": str(error)}), 400

@app.route("/api/firmware/analyze", methods=["POST"])
def analyze_uploaded_firmware():
    payload = request.get_json(silent=True) or {}
    try:
        analysis = analyze_firmware(payload.get("source", ""))
        preset_id = payload.get("preset_id")
        if preset_id:
            analysis["findings"] = verify_firmware_against_preset(analysis, preset_catalog.get(preset_id))
        return jsonify(analysis)
    except (ValueError, CatalogError) as error:
        return jsonify({"status": "INVALID_INPUT", "message": str(error)}), 400

@app.route("/api/eda/import", methods=["POST"])
def import_eda_graph():
    payload = request.get_json(silent=True) or {}
    try:
        fmt = payload.get("format")
        if fmt == "kicad_legacy":
            return jsonify(import_kicad_legacy_netlist(payload.get("content", "")))
        if fmt == "spice":
            return jsonify(import_spice_netlist(payload.get("content", "")))
        raise EdaImportError("format must be 'kicad_legacy' or 'spice'.")
    except EdaImportError as error:
        return jsonify({"status": "INVALID_INPUT", "message": str(error)}), 400

@app.route("/api/instruments/evidence", methods=["POST"])
def add_instrument_evidence():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify({"evidence": instrument_registry.normalize(payload)})
    except ValueError as error:
        return jsonify({"status": "INVALID_INPUT", "message": str(error)}), 400

@app.route("/api/sessions/<session_id>/instruments/evidence", methods=["POST"])
def add_session_instrument_evidence(session_id):
    """Use a measured continuity pass as graph evidence for one session."""
    payload = request.get_json(silent=True) or {}
    try:
        evidence = instrument_registry.normalize(payload)
        if evidence["kind"] != "continuity" or not evidence["connected"]:
            return jsonify({"status": "INDETERMINATE", "evidence": evidence,
                            "message": "Only a positive continuity reading can add a graph connection."}), 422
        state = session_manager.get(session_id).add_instrumented_connection(
            evidence["from"], evidence["to"], evidence["adapter"], evidence.get("wire_color")
        )
        return jsonify({"state": state, "evidence": evidence})
    except (ValueError, SessionError) as error:
        return jsonify({"status": "INVALID_INPUT", "message": str(error)}), 400

@app.route("/api/components/verify", methods=["POST"])
def verify_component_envelopes():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(digital_twin_engine.evaluate(payload.get("components", [])))
    except ValueError as error:
        return jsonify({"status": "INVALID_INPUT", "message": str(error)}), 400

@app.route("/api/simulation/operating-point", methods=["POST"])
def simulate_operating_point():
    payload = request.get_json(silent=True) or {}
    return jsonify(run_operating_point(
        payload.get("netlist", ""), payload.get("expected_node_ranges_v"), payload.get("timeout_seconds", 3.0)
    ))

@app.route("/api/benchmarks/replay", methods=["POST"])
def replay_benchmark_suite():
    payload = request.get_json(silent=True) or {}
    workspace = Path(__file__).resolve().parent
    directory = (workspace / payload.get("directory", "benchmarks/fixtures")).resolve()
    try:
        directory.relative_to(workspace)
    except ValueError:
        return jsonify({"status": "INVALID_INPUT", "message": "Benchmark directory must be inside the workspace."}), 400
    try:
        return jsonify(replay_suite(directory))
    except BenchmarkError as error:
        return jsonify({"status": "INVALID_INPUT", "message": str(error)}), 400

@app.route("/api/sessions/<session_id>/confirmations", methods=["POST"])
def confirm_session_connection(session_id):
    payload = request.get_json(silent=True) or {}
    try:
        if not isinstance(payload.get("accepted"), bool):
            raise SessionError("accepted must be a boolean.")
        state = session_manager.get(session_id).confirm(
            payload.get("from"), payload.get("to"), payload["accepted"], payload.get("wire_color")
        )
        return jsonify(state)
    except SessionError as error:
        return jsonify({"status": "INVALID_INPUT", "message": str(error)}), 400

if socketio is not None:
    @socketio.on("join_session")
    def join_debug_session(data):
        session_id = (data or {}).get("session_id")
        try:
            session = session_manager.get(session_id)
        except SessionError:
            return {"status": "NOT_FOUND"}
        join_room(f"session:{session_id}")
        return session.state()

@app.route("/api/snapshot", methods=["POST"])
def take_snapshot():
    """Take a snapshot of the current frame with annotations."""
    with frame_lock:
        if latest_frame is not None:
            import datetime as dt
            ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            snap_dir = os.path.join(os.path.dirname(__file__), "snapshots")
            os.makedirs(snap_dir, exist_ok=True)
            path = os.path.join(snap_dir, f"snap_{ts}.jpg")
            cv2.imwrite(path, latest_frame)
            return jsonify({"status": "success", "path": path})
    return jsonify({"status": "error", "message": "No frame available"})

@app.route("/api/health")
def health():
    """System health check for demo monitoring."""
    return jsonify({
        "status": "ok",
        "camera": camera_connected,
        "model_loaded": model_master is not None,
        "model_backend": model_backend,
        "model_verified": model_verified,
        "model_artifact_id": model_artifact_id,
        "model_selection_reason": model_selection_reason,
        "vlm_active": circuit_analyzer.api_available,
        "vlm_analyses": circuit_analyzer.analysis_count,
        "infer_fps": infer_fps,
        "infer_ms": infer_ms,
        "frame_width": FRAME_WIDTH,
        "frame_height": FRAME_HEIGHT,
        "streamer_frames": global_streamer.frame_count if global_streamer else 0,
        "camera_capture_health": global_streamer.health() if global_streamer else {"status": "UNAVAILABLE"},
        "graph_sessions": session_manager.count(),
        "audit_logging": True,
        "calibration": calibration_mat.state.as_dict() if calibration_mat.state else None,
        "realtime_transport": "websocket" if socketio is not None else "rest_fallback"
    })

@app.route("/api/detections")
def get_detections():
    with frame_lock:
        return jsonify({
            "detections": latest_detections,
            "timestamp": latest_timestamp,
            "camera_connected": camera_connected,
            "infer_fps": infer_fps,
            "infer_ms": infer_ms,
            "verification": latest_verification_report
        })

global_streamer = None

def main():
    global camera_base_url, global_streamer
    parser = argparse.ArgumentParser(description="CircuitPulse Production Backend")
    parser.add_argument("--camera", type=str, default="0", help="Camera source (0 for USB, http://IP:PORT/video for IP Webcam)")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address; use 0.0.0.0 only for an intentional LAN demo")
    args = parser.parse_args()
    
    try:
        src = normalize_camera_source(args.camera)
    except CameraSourceError as error:
        parser.error(str(error))
    if isinstance(src, str) and src.startswith(("http://", "https://")):
        camera_base_url = src
        
    print(f"Initializing camera source: {src}")
    load_models()
    global_streamer = VideoStreamer(src=src).start()
    threading.Thread(target=inference_loop, args=(global_streamer,), daemon=True).start()
    if socketio is not None:
        socketio.run(app, host=args.host, port=port, allow_unsafe_werkzeug=True)
    else:
        app.run(host=args.host, port=port, threaded=True)

if __name__ == "__main__":
    main()
