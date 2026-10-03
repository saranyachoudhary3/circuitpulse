"""Flask API integration tests for CircuitPulse v2 REST endpoints and WebSocket events.

Fully hermetic:
- Uses Flask's test_client() and SocketIO test_client()
- Requires zero physical cameras, real neural models, or network access
- Uses temporary directories for audit logs and cleans up all state in tearDown
- Generates synthetic in-memory ArUco images for calibration and module detection
"""

import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

import main
from logic.audit import SessionAuditLog


def make_synthetic_calibration_mat(width: int = 800, height: int = 600) -> bytes:
    """Generate in-memory JPEG bytes of a calibration mat with markers 0, 1, 2, 3."""
    canvas = np.ones((height, width, 3), dtype=np.uint8) * 255
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    positions = [
        (0, 50, 50),
        (1, 50, width - 150),
        (2, height - 150, width - 150),
        (3, height - 150, 50),
    ]
    for mid, y, x in positions:
        marker = cv2.aruco.generateImageMarker(dictionary, mid, 100)
        canvas[y:y + 100, x:x + 100] = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
    _, buf = cv2.imencode(".jpg", canvas)
    return buf.tobytes()


def make_synthetic_module_image(marker_id: int = 10, width: int = 300, height: int = 300) -> bytes:
    """Generate in-memory JPEG bytes containing one ArUco module marker."""
    canvas = np.ones((height, width, 3), dtype=np.uint8) * 255
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    marker = cv2.aruco.generateImageMarker(dictionary, marker_id, 100)
    canvas[50:150, 50:150] = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
    _, buf = cv2.imencode(".jpg", canvas)
    return buf.tobytes()


class BaseApiTestCase(unittest.TestCase):
    """Hermetic base test case ensuring clean state isolation."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.orig_audit_log = main.session_manager.audit_log
        main.session_manager.audit_log = SessionAuditLog(Path(self.tmpdir.name))
        main.session_manager._sessions.clear()

        self.orig_latest_frame = main.latest_frame
        self.orig_camera_base_url = main.camera_base_url
        self.orig_camera_connected = main.camera_connected
        self.orig_calib_state = main.calibration_mat.state
        self.orig_global_streamer = main.global_streamer
        self.orig_model_master = main.model_master
        self.orig_model_verified = main.model_verified
        self.orig_model_artifact_id = main.model_artifact_id

        main.latest_frame = None
        main.camera_base_url = None
        main.camera_connected = False
        main.calibration_mat.state = None
        main.global_streamer = None

        self.client = main.app.test_client()

    def tearDown(self):
        main.session_manager._sessions.clear()
        main.session_manager.audit_log = self.orig_audit_log
        self.tmpdir.cleanup()

        main.latest_frame = self.orig_latest_frame
        main.camera_base_url = self.orig_camera_base_url
        main.camera_connected = self.orig_camera_connected
        main.calibration_mat.state = self.orig_calib_state
        main.global_streamer = self.orig_global_streamer
        main.model_master = self.orig_model_master
        main.model_verified = self.orig_model_verified
        main.model_artifact_id = self.orig_model_artifact_id
        main.session_manager.set_camera_available(False)


class TestHealthAndMonitoring(BaseApiTestCase):
    """Test general system health, static files, frame snapshots, stream, and VLM endpoints."""

    def test_index_serves_html(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/html", res.content_type)
        res.close()

    def test_static_asset_serves_css(self):
        res = self.client.get("/styles.css")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/css", res.content_type)
        res.close()

    def test_static_asset_not_found(self):
        res = self.client.get("/nonexistent_asset_file.xyz")
        self.assertEqual(res.status_code, 404)
        res.close()

    def test_health_check_endpoint(self):
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("camera", data)
        self.assertIn("realtime_transport", data)
        self.assertIn("graph_sessions", data)

    def test_detections_endpoint(self):
        res = self.client.get("/api/detections")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["detections"], [])
        self.assertIn("camera_connected", data)

    def test_stream_returns_mjpeg_chunks(self):
        class DummyStreamer:
            def read(self, max_age_seconds=1.0):
                return np.zeros((20, 20, 3), dtype=np.uint8)

        main.global_streamer = DummyStreamer()
        res = self.client.get("/api/stream", buffered=False)
        self.assertEqual(res.status_code, 200)
        self.assertIn("multipart/x-mixed-replace", res.mimetype)
        first_chunk = next(res.response)
        self.assertTrue(len(first_chunk) > 0)
        self.assertIn(b"--frame", first_chunk)
        res.close()

    def test_snapshot_no_frame_returns_error(self):
        main.latest_frame = None
        res = self.client.post("/api/snapshot")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["message"], "No frame available")

    def test_snapshot_with_frame_success(self):
        main.latest_frame = np.zeros((40, 40, 3), dtype=np.uint8)
        with patch("cv2.imwrite", return_value=True):
            res = self.client.post("/api/snapshot")
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertEqual(data["status"], "success")
            self.assertIn("snapshots", data["path"])

    def test_focus_without_ip_camera(self):
        main.camera_base_url = None
        res = self.client.post("/api/focus")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["message"], "Not an IP Camera")

    def test_focus_with_ip_camera_success(self):
        main.camera_base_url = "http://192.168.1.50:8080/video"
        with patch("requests.get") as mock_get:
            res = self.client.post("/api/focus")
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertEqual(data["status"], "success")
            self.assertEqual(data["message"], "Focus triggered")
            mock_get.assert_called_once_with("http://192.168.1.50:8080/focus", timeout=2)

    def test_focus_with_ip_camera_failure(self):
        main.camera_base_url = "http://192.168.1.50:8080/video"
        with patch("requests.get", side_effect=Exception("Connection timed out")):
            res = self.client.post("/api/focus")
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertEqual(data["status"], "error")
            self.assertIn("Connection timed out", data["message"])

    def test_trigger_analyze(self):
        res = self.client.post("/api/analyze")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["message"], "Analysis triggered")

    def test_ask_valid_question(self):
        res = self.client.post("/api/ask", json={"question": "Is LED polarity correct?"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["message"], "Question queued for next analysis")

    def test_ask_missing_or_empty_question(self):
        res1 = self.client.post("/api/ask", json={"question": "   "})
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1.get_json()["status"], "error")

        res2 = self.client.post("/api/ask", json={})
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.get_json()["status"], "error")


class TestCatalogsAndReadiness(BaseApiTestCase):
    """Test presets, modules, ArUco identification, calibration mat, and readiness endpoints."""

    def test_list_presets(self):
        res = self.client.get("/api/presets")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["schema_version"], 1)
        self.assertGreaterEqual(len(data["presets"]), 6)
        preset_ids = {p["id"] for p in data["presets"]}
        self.assertIn("led_blink", preset_ids)

    def test_identify_presets_valid(self):
        res = self.client.post("/api/presets/identify", json={"components": ["arduino_uno", "resistor", "led"]})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("candidates", data)
        self.assertTrue(any(c["id"] == "led_blink" for c in data["candidates"]))

    def test_identify_presets_invalid_components_type(self):
        res = self.client.post("/api/presets/identify", json={"components": "not_a_list"})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["status"], "INVALID_INPUT")

    def test_identify_presets_non_string_elements(self):
        res = self.client.post("/api/presets/identify", json={"components": ["arduino_uno", 123]})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["status"], "INVALID_INPUT")

    def test_presets_repair_plan_valid(self):
        res = self.client.post("/api/presets/led_blink/repair-plan", json={"observed": []})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("actions", data)
        self.assertIn("next_action", data)
        self.assertIn("summary", data)

    def test_presets_repair_plan_unknown_preset(self):
        res = self.client.post("/api/presets/unknown_blueprint/repair-plan", json={"observed": []})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["status"], "INVALID_INPUT")

    def test_presets_repair_plan_invalid_observed_payload(self):
        res = self.client.post("/api/presets/led_blink/repair-plan", json={"observed": "not_a_list"})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["status"], "INVALID_INPUT")

    def test_list_modules(self):
        res = self.client.get("/api/modules")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["schema_version"], 1)
        self.assertGreaterEqual(len(data["modules"]), 14)

    def test_identify_modules_valid_fiducial(self):
        img_bytes = make_synthetic_module_image(10)
        res = self.client.post(
            "/api/modules/identify",
            data={"image": (io.BytesIO(img_bytes), "mod.jpg")},
            content_type="multipart/form-data"
        )
        self.assertEqual(res.status_code, 200)
        modules = res.get_json()["modules"]
        self.assertTrue(any(m.get("module_id") == "arduino_uno" for m in modules))

    def test_identify_modules_missing_file(self):
        res = self.client.post("/api/modules/identify")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["status"], "INVALID_INPUT")

    def test_identify_modules_corrupt_file(self):
        res = self.client.post(
            "/api/modules/identify",
            data={"image": (io.BytesIO(b"garbage not an image"), "mod.jpg")},
            content_type="multipart/form-data"
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["status"], "INVALID_INPUT")

    def test_calibration_valid_mat(self):
        img_bytes = make_synthetic_calibration_mat()
        res = self.client.post(
            "/api/calibration",
            data={"image": (io.BytesIO(img_bytes), "cal.jpg")},
            content_type="multipart/form-data"
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "PASS")
        self.assertIn("homography", data["calibration"])
        self.assertIsNotNone(main.calibration_mat.state)

    def test_calibration_missing_file(self):
        res = self.client.post("/api/calibration")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["status"], "INVALID_INPUT")

    def test_calibration_corrupt_file(self):
        res = self.client.post(
            "/api/calibration",
            data={"image": (io.BytesIO(b"not a valid image format"), "cal.jpg")},
            content_type="multipart/form-data"
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["status"], "INVALID_INPUT")

    def test_calibration_no_markers_error(self):
        blank = np.ones((600, 800, 3), dtype=np.uint8) * 255
        _, buf = cv2.imencode(".jpg", blank)
        res = self.client.post(
            "/api/calibration",
            data={"image": (io.BytesIO(buf.tobytes()), "cal.jpg")},
            content_type="multipart/form-data"
        )
        self.assertEqual(res.status_code, 422)
        data = res.get_json()
        self.assertEqual(data["status"], "INDETERMINATE")

    def test_readiness_valid_default(self):
        res = self.client.get("/api/readiness")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("automatic_verification", data)
        self.assertIn("blockers", data)

    def test_readiness_valid_preset(self):
        res = self.client.get("/api/readiness?preset_id=led_blink")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["preset"]["id"], "led_blink")

    def test_readiness_invalid_preset(self):
        res = self.client.get("/api/readiness?preset_id=nonexistent_preset")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["status"], "INVALID_INPUT")


class TestDomainAnalysisAndSimulations(BaseApiTestCase):
    """Test netlist verification, circuit IR, firmware analysis, EDA, instruments, simulation, and benchmarks."""

    def test_netlist_verify_valid(self):
        netlist = {
            "components": [
                {"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}},
                {"id": "R1", "type": "resistor", "value_ohms": 220, "pins": {"1": "VCC", "2": "LED_A"}},
                {"id": "D1", "type": "led", "pins": {"anode": "LED_A", "cathode": "GND"}},
            ]
        }
        res = self.client.post("/api/netlist/verify", json=netlist)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["status"], "PASS")

    def test_netlist_verify_missing_payload(self):
        res = self.client.post("/api/netlist/verify", data="not json", content_type="text/plain")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["status"], "INVALID_INPUT")

    def test_netlist_verify_invalid_schema(self):
        res = self.client.post("/api/netlist/verify", json={"components": "not_a_list"})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["status"], "INVALID_INPUT")

    def test_circuit_analyze_valid(self):
        circuit = {
            "components": [
                {"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}},
                {"id": "R1", "type": "resistor", "value_ohms": 220, "pins": {"1": "VCC", "2": "LED_A"}},
                {"id": "D1", "type": "led", "pins": {"anode": "LED_A", "cathode": "GND"}},
            ]
        }
        res = self.client.post("/api/circuit/analyze", json=circuit)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["status"], "PASS")

    def test_circuit_analyze_missing_payload(self):
        res = self.client.post("/api/circuit/analyze", data="bad", content_type="text/plain")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["status"], "INVALID_INPUT")

    def test_circuit_analyze_invalid_payload(self):
        res = self.client.post("/api/circuit/analyze", json={"components": "not_a_list"})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["status"], "INVALID_INPUT")

    def test_firmware_analyze_valid(self):
        code = "void setup() { pinMode(13, OUTPUT); digitalWrite(13, HIGH); }"
        res = self.client.post("/api/firmware/analyze", json={"source": code})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("13", data["pins"])
        self.assertEqual(data["pins"]["13"]["mode"], "OUTPUT")

    def test_firmware_analyze_with_preset_conflict(self):
        code = "void setup() { pinMode(D13, INPUT); }"
        res = self.client.post("/api/firmware/analyze", json={"source": code, "preset_id": "led_blink"})
        self.assertEqual(res.status_code, 200)
        findings = res.get_json().get("findings", [])
        self.assertTrue(any(f["code"] == "FIRMWARE_PIN_MODE_CONFLICT" for f in findings))

    def test_firmware_analyze_empty_source(self):
        res = self.client.post("/api/firmware/analyze", json={"source": ""})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["status"], "INVALID_INPUT")

    def test_firmware_analyze_unknown_preset(self):
        res = self.client.post("/api/firmware/analyze", json={"source": "void setup() {}", "preset_id": "bad_preset"})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["status"], "INVALID_INPUT")

    def test_eda_import_kicad_valid(self):
        kicad_text = (
            "(export (version D)\n"
            "  (nets\n"
            "    (net (code 1) (name \"VCC\")\n"
            "      (node (ref \"R1\") (pin \"1\"))\n"
            "      (node (ref \"D1\") (pin \"A\")))\n"
            "  )\n)"
        )
        res = self.client.post("/api/eda/import", json={"format": "kicad_legacy", "content": kicad_text})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["format"], "kicad_legacy")
        self.assertEqual(len(data["nets"]), 1)

    def test_eda_import_spice_valid(self):
        spice_text = "R1 VCC LED_A 220\nD1 LED_A GND LED"
        res = self.client.post("/api/eda/import", json={"format": "spice", "content": spice_text})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["format"], "spice")
        self.assertGreaterEqual(len(data["components"]), 2)

    def test_eda_import_unknown_format(self):
        res = self.client.post("/api/eda/import", json={"format": "eagle", "content": "..."})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["status"], "INVALID_INPUT")

    def test_eda_import_invalid_content(self):
        res = self.client.post("/api/eda/import", json={"format": "kicad_legacy", "content": "no nets here"})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["status"], "INVALID_INPUT")

    def test_instruments_evidence_valid(self):
        payload = {"kind": "continuity", "from": "uno:13", "to": "led:anode", "connected": True}
        res = self.client.post("/api/instruments/evidence", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["evidence"]["kind"], "continuity")
        self.assertEqual(data["evidence"]["confidence"], 1.0)

    def test_instruments_evidence_invalid_kind(self):
        payload = {"kind": "unsupported_sensor", "from": "uno:13", "to": "led:anode"}
        res = self.client.post("/api/instruments/evidence", json=payload)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["status"], "INVALID_INPUT")

    def test_instruments_evidence_missing_fields(self):
        payload = {"kind": "continuity", "from": "uno:13"}
        res = self.client.post("/api/instruments/evidence", json=payload)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["status"], "INVALID_INPUT")

    def test_components_verify_valid(self):
        payload = {"components": [{"module_id": "rc522", "supply_voltage": 3.3}]}
        res = self.client.post("/api/components/verify", json=payload)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["status"], "PASS")

    def test_components_verify_incompatible_voltage(self):
        payload = {"components": [{"module_id": "rc522", "supply_voltage": 5.0}]}
        res = self.client.post("/api/components/verify", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "FAIL")
        self.assertTrue(any(f["code"] == "VOLTAGE_INCOMPATIBLE" for f in data["findings"]))

    def test_components_verify_invalid_type(self):
        res = self.client.post("/api/components/verify", json={"components": "not_a_list"})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["status"], "INVALID_INPUT")

    def test_simulation_operating_point_valid(self):
        res = self.client.post("/api/simulation/operating-point", json={"netlist": "R1 1 0 1k\n.op\n.end"})
        self.assertEqual(res.status_code, 200)
        self.assertIn(res.get_json().get("status"), ["PASS", "FAIL", "INDETERMINATE"])

    def test_simulation_operating_point_forbidden_directive(self):
        res = self.client.post("/api/simulation/operating-point", json={"netlist": ".control\nrun\n.endc"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["status"], "FAIL")

    def test_benchmarks_replay_valid(self):
        res = self.client.post("/api/benchmarks/replay", json={"directory": "benchmarks/fixtures"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertGreaterEqual(data["total"], 2)
        self.assertIn("accuracy", data)

    def test_benchmarks_replay_directory_escape(self):
        res = self.client.post("/api/benchmarks/replay", json={"directory": "../../outside"})
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertEqual(data["status"], "INVALID_INPUT")
        self.assertEqual(data["message"], "Benchmark directory must be inside the workspace.")

    def test_benchmarks_replay_nonexistent_directory(self):
        res = self.client.post("/api/benchmarks/replay", json={"directory": "benchmarks/nonexistent_dir"})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["status"], "INVALID_INPUT")


class TestSessionLifecycleAndOperations(BaseApiTestCase):
    """Test session lifecycle endpoints, valid/invalid inputs, and full end-to-end flow."""

    def test_create_session_valid(self):
        res = self.client.post("/api/sessions", json={"preset_id": "led_blink"})
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertIn("session_id", data)
        self.assertEqual(data["preset"]["id"], "led_blink")

    def test_create_session_unknown_preset(self):
        res = self.client.post("/api/sessions", json={"preset_id": "nonexistent_preset"})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["status"], "INVALID_INPUT")

    def test_get_session_state_valid(self):
        sid = self.client.post("/api/sessions", json={"preset_id": "led_blink"}).get_json()["session_id"]
        res = self.client.get(f"/api/sessions/{sid}/state")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["session_id"], sid)

    def test_get_session_state_unknown_id(self):
        res = self.client.get("/api/sessions/unknown-session-id/state")
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.get_json()["status"], "NOT_FOUND")

    def test_session_observations_valid(self):
        sid = self.client.post("/api/sessions", json={"preset_id": "led_blink"}).get_json()["session_id"]
        res = self.client.post(
            f"/api/sessions/{sid}/observations",
            json={"connections": [{"from": "arduino:D13", "to": "bb:r7a", "confidence": 0.95}]}
        )
        self.assertEqual(res.status_code, 200)

    def test_session_observations_confidence_out_of_range(self):
        sid = self.client.post("/api/sessions", json={"preset_id": "led_blink"}).get_json()["session_id"]
        res = self.client.post(
            f"/api/sessions/{sid}/observations",
            json={"connections": [{"from": "arduino:D13", "to": "bb:r7a", "confidence": 3.14}]}
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["status"], "INVALID_INPUT")

    def test_session_observations_non_numeric_confidence(self):
        sid = self.client.post("/api/sessions", json={"preset_id": "led_blink"}).get_json()["session_id"]
        res = self.client.post(
            f"/api/sessions/{sid}/observations",
            json={"connections": [{"from": "arduino:D13", "to": "bb:r7a", "confidence": "high"}]}
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["status"], "INVALID_INPUT")

    def test_session_observations_non_list_connections(self):
        sid = self.client.post("/api/sessions", json={"preset_id": "led_blink"}).get_json()["session_id"]
        res = self.client.post(
            f"/api/sessions/{sid}/observations",
            json={"connections": "not_a_list"}
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["status"], "INVALID_INPUT")

    def test_session_confirmations_valid(self):
        sid = self.client.post("/api/sessions", json={"preset_id": "led_blink"}).get_json()["session_id"]
        res = self.client.post(
            f"/api/sessions/{sid}/confirmations",
            json={"from": "arduino:D13", "to": "bb:r7a", "accepted": True}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        observed_ids = {edge["id"] for edge in data["graph"]["observed"]}
        self.assertIn("arduino:D13 <-> bb:r7a", observed_ids)

    def test_session_confirmations_invalid_accepted_type(self):
        sid = self.client.post("/api/sessions", json={"preset_id": "led_blink"}).get_json()["session_id"]
        res = self.client.post(
            f"/api/sessions/{sid}/confirmations",
            json={"from": "arduino:D13", "to": "bb:r7a", "accepted": "yes_confirm"}
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["status"], "INVALID_INPUT")

    def test_session_instruments_evidence_positive(self):
        sid = self.client.post("/api/sessions", json={"preset_id": "led_blink"}).get_json()["session_id"]
        payload = {"kind": "continuity", "from": "arduino:D13", "to": "bb:r7a", "connected": True}
        res = self.client.post(f"/api/sessions/{sid}/instruments/evidence", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("state", data)
        self.assertEqual(data["evidence"]["connected"], True)

    def test_session_instruments_evidence_negative_rejected(self):
        sid = self.client.post("/api/sessions", json={"preset_id": "led_blink"}).get_json()["session_id"]
        payload = {"kind": "continuity", "from": "arduino:D13", "to": "bb:r7a", "connected": False}
        res = self.client.post(f"/api/sessions/{sid}/instruments/evidence", json=payload)
        self.assertEqual(res.status_code, 422)
        data = res.get_json()
        self.assertEqual(data["status"], "INDETERMINATE")

    def test_session_instruments_evidence_unknown_session(self):
        payload = {"kind": "continuity", "from": "arduino:D13", "to": "bb:r7a", "connected": True}
        res = self.client.post("/api/sessions/unknown_sid/instruments/evidence", json=payload)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["status"], "INVALID_INPUT")

    def test_session_netlist_verify_stale_revision(self):
        sid = self.client.post("/api/sessions", json={"preset_id": "led_blink"}).get_json()["session_id"]
        netlist = {"components": [{"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}}]}
        res = self.client.post(
            f"/api/sessions/{sid}/netlist/verify",
            json={"netlist": netlist, "graph_revision": 999, "graph_fingerprint": "stale", "terminal_nets": {}}
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["status"], "INVALID_INPUT")

    def test_session_netlist_verify_unknown_session(self):
        res = self.client.post(
            "/api/sessions/unknown_sid/netlist/verify",
            json={"netlist": {}, "graph_revision": 0, "graph_fingerprint": "", "terminal_nets": {}}
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["status"], "INVALID_INPUT")

    def test_session_repair_plan_unknown_session(self):
        res = self.client.get("/api/sessions/unknown_sid/repair-plan")
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.get_json()["status"], "NOT_FOUND")

    def test_session_audit_verify_unknown_session(self):
        res = self.client.get("/api/sessions/unknown_sid/audit/verify")
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.get_json()["status"], "NOT_FOUND")

    def test_session_vision_graph_uncalibrated_rejected(self):
        sid = self.client.post("/api/sessions", json={"preset_id": "led_blink"}).get_json()["session_id"]
        res = self.client.post(f"/api/sessions/{sid}/vision-graph", json={"contract_version": 1})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["status"], "INVALID_INPUT")

    def test_session_vision_graph_invalid_contract_version(self):
        sid = self.client.post("/api/sessions", json={"preset_id": "led_blink"}).get_json()["session_id"]
        res = self.client.post(f"/api/sessions/{sid}/vision-graph", json={"contract_version": 99})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["status"], "INVALID_INPUT")

    def test_session_lifecycle_end_to_end(self):
        """Complete 7-step lifecycle: create -> observe -> confirm -> state -> verify -> repair -> audit."""
        main.session_manager.set_camera_available(True)

        # 1. Create session
        res_create = self.client.post("/api/sessions", json={"preset_id": "led_blink"})
        self.assertEqual(res_create.status_code, 201)
        session_state = res_create.get_json()
        sid = session_state["session_id"]
        self.assertEqual(session_state["status"], "INCOMPLETE")
        self.assertEqual(session_state["electrical_status"], "INCOMPLETE")
        self.assertEqual(session_state["next_action"]["kind"], "add")

        # 2. Visual observations (simulate 5 frames of high confidence observation)
        obs_payload = {"connections": [{"from": "arduino:D13", "to": "bb:r7a", "confidence": 0.95}]}
        for _ in range(5):
            res_obs = self.client.post(f"/api/sessions/{sid}/observations", json=obs_payload)
            self.assertEqual(res_obs.status_code, 200)

        obs_state = res_obs.get_json()
        self.assertEqual(obs_state["status"], "INDETERMINATE")
        observed_ids = {e["id"] for e in obs_state["graph"]["observed"]}
        self.assertIn("arduino:D13 <-> bb:r7a", observed_ids)

        # 3. Confirmations (confirm all required connections for led_blink)
        connections_to_confirm = [
            ("arduino:D13", "bb:r7a"),
            ("bb:r7e", "led:anode"),
            ("led:cathode", "arduino:GND"),
        ]
        for src, dst in connections_to_confirm:
            res_conf = self.client.post(
                f"/api/sessions/{sid}/confirmations",
                json={"from": src, "to": dst, "accepted": True}
            )
            self.assertEqual(res_conf.status_code, 200)

        # 4. State query
        res_state = self.client.get(f"/api/sessions/{sid}/state")
        self.assertEqual(res_state.status_code, 200)
        current_state = res_state.get_json()
        graph_revision = current_state["graph_revision"]
        graph_fingerprint = current_state["graph_fingerprint"]
        self.assertGreater(graph_revision, 0)
        self.assertTrue(bool(graph_fingerprint))

        # 5. Netlist verify on current revision
        safe_netlist = {
            "components": [
                {"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}},
                {"id": "R1", "type": "resistor", "value_ohms": 220, "pins": {"1": "VCC", "2": "LED_A"}},
                {"id": "D1", "type": "led", "pins": {"anode": "LED_A", "cathode": "GND"}},
            ]
        }
        terminal_nets = {
            "arduino:D13": "VCC",
            "bb:r7a": "VCC",
            "bb:r7e": "LED_A",
            "led:anode": "LED_A",
            "led:cathode": "GND",
            "arduino:GND": "GND",
        }
        verify_payload = {
            "netlist": safe_netlist,
            "graph_revision": graph_revision,
            "graph_fingerprint": graph_fingerprint,
            "terminal_nets": terminal_nets,
        }
        res_verify = self.client.post(f"/api/sessions/{sid}/netlist/verify", json=verify_payload)
        self.assertEqual(res_verify.status_code, 200)
        verified_state = res_verify.get_json()
        self.assertEqual(verified_state["status"], "PASS")
        self.assertEqual(verified_state["electrical_status"], "PASS")
        self.assertEqual(verified_state["next_action"]["kind"], "complete")

        # 6. Repair plan on authoritative passing session
        res_repair = self.client.get(f"/api/sessions/{sid}/repair-plan")
        self.assertEqual(res_repair.status_code, 200)
        repair_plan = res_repair.get_json()
        self.assertEqual(repair_plan["session_id"], sid)
        self.assertEqual(repair_plan["status"], "PASS")
        self.assertEqual(repair_plan["actions"], [])

        # 7. Audit hash chain verify
        res_audit = self.client.get(f"/api/sessions/{sid}/audit/verify")
        self.assertEqual(res_audit.status_code, 200)
        audit_result = res_audit.get_json()
        self.assertEqual(audit_result["status"], "PASS")
        self.assertGreaterEqual(audit_result["records"], 5)
        self.assertTrue(bool(audit_result["tail_hash"]))


class TestWebSocketEvents(BaseApiTestCase):
    """Test WebSocket events when flask_socketio is available."""

    def test_websocket_join_session_valid(self):
        if main.socketio is None:
            self.skipTest("Flask-SocketIO is not installed")
        session_state = self.client.post("/api/sessions", json={"preset_id": "led_blink"}).get_json()
        sid = session_state["session_id"]

        sio_client = main.socketio.test_client(main.app)
        self.assertTrue(sio_client.is_connected())
        response = sio_client.emit("join_session", {"session_id": sid}, callback=True)
        self.assertIsNotNone(response)
        self.assertEqual(response["session_id"], sid)
        sio_client.disconnect()

    def test_websocket_join_session_unknown_id(self):
        if main.socketio is None:
            self.skipTest("Flask-SocketIO is not installed")
        sio_client = main.socketio.test_client(main.app)
        response = sio_client.emit("join_session", {"session_id": "unknown_sid"}, callback=True)
        self.assertEqual(response, {"status": "NOT_FOUND"})
        sio_client.disconnect()


if __name__ == "__main__":
    unittest.main()
class TestExtendedIntegrationCases(BaseApiTestCase):
    def test_health_without_camera(self):
        main.camera_connected = False
        res = self.client.get("/api/health")
        data = res.get_json()
        self.assertFalse(data.get("camera", True)) # In main.py: "camera": camera_connected

    def test_readiness_without_camera(self):
        main.camera_connected = False
        res = self.client.get("/api/readiness")
        data = res.get_json()
        self.assertFalse(data["automatic_verification"])
        self.assertTrue(any(b["code"] == "CAMERA_UNAVAILABLE" for b in data["blockers"]))

    def test_sessions_post_invalid_json(self):
        res = self.client.post("/api/sessions", data="not json", content_type="text/plain")
        self.assertEqual(res.status_code, 400)

    def test_sessions_post_empty_json(self):
        res = self.client.post("/api/sessions", json={})
        self.assertEqual(res.status_code, 400)

    def test_identify_presets_empty_components(self):
        res = self.client.post("/api/presets/identify", json={"components": []})
        self.assertEqual(res.status_code, 200)

    def test_identify_presets_missing_components(self):
        res = self.client.post("/api/presets/identify", json={})
        self.assertEqual(res.status_code, 200)

    def test_repair_plan_missing_observed(self):
        res = self.client.post("/api/presets/led_blink/repair-plan", json={})
        self.assertEqual(res.status_code, 200)

    def test_netlist_verify_empty_components(self):
        res = self.client.post("/api/netlist/verify", json={"components": []})
        self.assertEqual(res.status_code, 400)

    def test_firmware_analyze_missing_source(self):
        res = self.client.post("/api/firmware/analyze", json={})
        self.assertEqual(res.status_code, 400)

    def test_eda_import_missing_format(self):
        res = self.client.post("/api/eda/import", json={"content": "..."})
        self.assertEqual(res.status_code, 400)

    def test_circuit_analyze_empty_components(self):
        res = self.client.post("/api/circuit/analyze", json={"components": []})
        self.assertEqual(res.status_code, 400)

    def test_simulation_operating_point_missing_netlist(self):
        res = self.client.post("/api/simulation/operating-point", json={})
        self.assertEqual(res.status_code, 200)

    def test_benchmarks_replay_missing_directory(self):
        res = self.client.post("/api/benchmarks/replay", json={})
        self.assertEqual(res.status_code, 200)

    def test_session_observations_missing_connections(self):
        sid = self.client.post("/api/sessions", json={"preset_id": "led_blink"}).get_json()["session_id"]
        res = self.client.post(f"/api/sessions/{sid}/observations", json={})
        self.assertEqual(res.status_code, 400)

    def test_session_confirmations_missing_fields(self):
        sid = self.client.post("/api/sessions", json={"preset_id": "led_blink"}).get_json()["session_id"]
        res = self.client.post(f"/api/sessions/{sid}/confirmations", json={})
        self.assertEqual(res.status_code, 400)

    def test_session_netlist_verify_missing_netlist(self):
        sid = self.client.post("/api/sessions", json={"preset_id": "led_blink"}).get_json()["session_id"]
        res = self.client.post(f"/api/sessions/{sid}/netlist/verify", json={})
        self.assertEqual(res.status_code, 400)

    def test_session_instruments_evidence_missing_kind(self):
        sid = self.client.post("/api/sessions", json={"preset_id": "led_blink"}).get_json()["session_id"]
        res = self.client.post(f"/api/sessions/{sid}/instruments/evidence", json={})
        self.assertEqual(res.status_code, 400)

    def test_calibration_no_file(self):
        res = self.client.post("/api/calibration", data={})
        self.assertEqual(res.status_code, 400)

