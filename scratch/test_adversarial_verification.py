"""Adversarial stress and verification harness for CircuitPulse v2.
Run by Challenger 1 to empirically verify:
1. Benchmark suite robustness and replay engine edge cases
2. API test negative input paths in main.py
3. Detector test assertions and calculation accuracy
"""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


import cv2
import numpy as np

from logic.benchmark import (
    BenchmarkError,
    _fixture_evidence,
    _coverage,
    _operational_gates,
    replay_fixture,
    replay_suite,
)
from logic.catalog import PresetCatalog, CatalogError
from detectors.resistor import (
    COLOR_DIGITS,
    COLOR_MULTIPLIERS,
    COLOR_TOLERANCES,
    ResistorDecoder,
    classify_pixel_color,
    snap_to_e12,
    format_ohms,
)
from detectors.wires import WireTracer
from detectors.tracker import Tracker
from detectors.zoom import AutoZoom
from detectors.memory import WireMemory
from camera import VideoStreamer, normalize_camera_source, CameraSourceError
import main


class TestBenchmarkAdversarial(unittest.TestCase):
    """Stress test benchmark suite and replay engine against corrupted and adversarial inputs."""

    def setUp(self):
        self.fixtures_dir = Path("benchmarks/fixtures")
        self.temp_dir = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_01_all_existing_fixtures_replay_correctly(self):
        """Every existing fixture in benchmarks/fixtures must pass replay with 0 false-safes."""
        files = sorted(self.fixtures_dir.glob("*.json"))
        self.assertGreaterEqual(len(files), 24, "Fewer than 24 benchmark fixtures found")
        for f in files:
            res = replay_fixture(f)
            self.assertEqual(
                res["actual_status"],
                res["expected_status"],
                f"Fixture {f.name} status mismatch: expected {res['expected_status']}, got {res['actual_status']}"
            )
            self.assertTrue(res["passed"], f"Fixture {f.name} did not pass")
            self.assertFalse(res["false_safe"], f"Fixture {f.name} had false_safe=True!")

    def test_02_replay_suite_reports_development_ready(self):
        """replay_suite on benchmarks/fixtures must yield development_ready=True and false_safe_count=0."""
        result = replay_suite(self.fixtures_dir)
        self.assertTrue(result["development_ready"], "development_ready is False")
        self.assertEqual(result["false_safe_count"], 0, "false_safe_count > 0")
        self.assertEqual(result["passed"], result["total"], f"Passed {result['passed']} out of {result['total']}")

    def test_03_corrupted_json_raises_benchmark_error(self):
        """Corrupted JSON must raise BenchmarkError."""
        bad_json = self.work_dir / "corrupted.json"
        bad_json.write_text("{this is not valid json", encoding="utf-8")
        with self.assertRaises(BenchmarkError) as ctx:
            replay_fixture(bad_json)
        self.assertIn("Cannot load fixture", str(ctx.exception))

    def test_04_missing_preset_id_raises_key_error(self):
        """Missing preset_id in fixture must raise KeyError."""
        bad_file = self.work_dir / "missing_preset.json"
        bad_file.write_text(json.dumps({"expected_status": "PASS"}), encoding="utf-8")
        with self.assertRaises(KeyError):
            replay_fixture(bad_file)

    def test_05_unknown_preset_id_raises_catalog_error(self):
        """Unknown preset_id must raise CatalogError when looking up in catalog."""
        bad_file = self.work_dir / "unknown_preset.json"
        bad_file.write_text(json.dumps({"preset_id": "non_existent_preset", "expected_status": "PASS"}), encoding="utf-8")
        with self.assertRaises(CatalogError):
            replay_fixture(bad_file)

    def test_06_malformed_netlist_raises_benchmark_error(self):
        """Fixture with invalid netlist must raise BenchmarkError."""
        bad_file = self.work_dir / "bad_netlist.json"
        fixture_data = {
            "preset_id": "led_blink",
            "netlist": {"components": [{"id": "R1", "type": "invalid_type", "pins": {}}]},
            "expected_status": "PASS"
        }
        bad_file.write_text(json.dumps(fixture_data), encoding="utf-8")
        with self.assertRaises(BenchmarkError) as ctx:
            replay_fixture(bad_file)
        self.assertIn("Invalid netlist", str(ctx.exception))

    def test_07_physical_fixture_path_traversal_blocked(self):
        """Physical fixture with capture_path traversing outside directory must raise BenchmarkError."""
        bad_file = self.work_dir / "escape.json"
        fixture_data = {
            "preset_id": "led_blink",
            "evidence": {
                "class": "held_out_physical",
                "capture_session_id": "sess_1",
                "operator": "test_op",
                "capture_path": "../../secret.txt",
                "capture_sha256": "a" * 64
            },
            "expected_status": "PASS"
        }
        bad_file.write_text(json.dumps(fixture_data), encoding="utf-8")
        with self.assertRaises(BenchmarkError) as ctx:
            replay_fixture(bad_file)
        self.assertIn("escapes its fixture directory", str(ctx.exception))

    def test_08_physical_fixture_missing_sha256_or_fields(self):
        """Physical fixture missing sha256 or operator must raise BenchmarkError."""
        bad_file = self.work_dir / "bad_evidence.json"
        fixture_data = {
            "preset_id": "led_blink",
            "evidence": {
                "class": "held_out_physical",
                "capture_session_id": "sess_1",
                "capture_path": "valid.bin",
                "capture_sha256": "too_short"
            },
            "expected_status": "PASS"
        }
        bad_file.write_text(json.dumps(fixture_data), encoding="utf-8")
        with self.assertRaises(BenchmarkError) as ctx:
            replay_fixture(bad_file)
        self.assertIn("requires capture_session_id, operator", str(ctx.exception))

    def test_09_false_safe_detection_mechanism(self):
        """If a faulty circuit is incorrectly marked expected_status='FAULT' but results in 'PASS', false_safe must be True."""
        # Create a synthetic fixture that achieves PASS state but has expected_status: FAULT
        complete_fixture = json.loads((self.fixtures_dir / "led_blink_complete.json").read_text(encoding="utf-8"))
        complete_fixture["expected_status"] = "FAULT"
        bad_file = self.work_dir / "synthetic_false_safe.json"
        bad_file.write_text(json.dumps(complete_fixture), encoding="utf-8")

        res = replay_fixture(bad_file)
        self.assertEqual(res["actual_status"], "PASS")
        self.assertEqual(res["expected_status"], "FAULT")
        self.assertTrue(res["false_safe"], "Replay engine failed to flag false_safe!")
        self.assertFalse(res["passed"])

    def test_10_missing_connections_in_fault_fixture(self):
        """Verify what happens if a fault fixture has no confirmations and empty frames."""
        # In a short fixture, if confirmations are empty, the session remains INCOMPLETE
        fixture_data = {
            "preset_id": "led_blink",
            "fault_class": "direct_short",
            "frames": [],
            "confirmations": [],
            "expected_status": "FAULT"
        }
        bad_file = self.work_dir / "empty_fault.json"
        bad_file.write_text(json.dumps(fixture_data), encoding="utf-8")
        res = replay_fixture(bad_file)
        # Status will be INCOMPLETE, not FAULT, so passed=False and false_safe=False
        self.assertEqual(res["actual_status"], "INCOMPLETE")
        self.assertFalse(res["passed"])
        self.assertFalse(res["false_safe"])


class TestApiNegativePathAdversarial(unittest.TestCase):
    """Verify that negative input tests in test_api.py genuinely trigger main.py error handling."""

    def setUp(self):
        self.client = main.app.test_client()

    def test_01_verify_api_400_responses_contain_invalid_input(self):
        """All 400 responses must return structured JSON status='INVALID_INPUT'."""
        endpoints_to_test = [
            ("POST", "/api/presets/identify", {"components": "bad_type"}),
            ("POST", "/api/presets/identify", {"components": [123]}),
            ("POST", "/api/presets/unknown/repair-plan", {"observed": []}),
            ("POST", "/api/presets/led_blink/repair-plan", {"observed": "not_list"}),
            ("POST", "/api/modules/identify", None),
            ("POST", "/api/calibration", None),
            ("GET", "/api/readiness?preset_id=unknown_preset", None),
            ("POST", "/api/netlist/verify", "plain_text"),
            ("POST", "/api/netlist/verify", {"components": "not_list"}),
            ("POST", "/api/circuit/analyze", "plain_text"),
            ("POST", "/api/circuit/analyze", {"components": "not_list"}),
            ("POST", "/api/firmware/analyze", {"source": ""}),
            ("POST", "/api/firmware/analyze", {"source": "void setup(){}", "preset_id": "invalid"}),
            ("POST", "/api/eda/import", {"format": "bad", "content": "xyz"}),
            ("POST", "/api/eda/import", {"format": "kicad_legacy", "content": "no nets"}),
            ("POST", "/api/instruments/evidence", {"kind": "unknown", "from": "a", "to": "b"}),
            ("POST", "/api/instruments/evidence", {"kind": "continuity"}),
            ("POST", "/api/components/verify", {"components": "not_list"}),
            ("POST", "/api/benchmarks/replay", {"directory": "../../escape"}),
            ("POST", "/api/benchmarks/replay", {"directory": "benchmarks/nonexistent"}),
            ("POST", "/api/sessions", {"preset_id": "unknown_preset"}),
            ("POST", "/api/sessions/unknown_sid/instruments/evidence", {"kind": "continuity", "from": "a", "to": "b", "connected": True}),
            ("POST", "/api/sessions/unknown_sid/netlist/verify", {"netlist": {}, "graph_revision": 0, "graph_fingerprint": "", "terminal_nets": {}}),
        ]

        for method, path, payload in endpoints_to_test:
            if method == "POST":
                if payload is None:
                    res = self.client.post(path)
                elif isinstance(payload, str):
                    res = self.client.post(path, data=payload, content_type="text/plain")
                else:
                    res = self.client.post(path, json=payload)
            else:
                res = self.client.get(path)

            self.assertEqual(
                res.status_code, 400,
                f"{method} {path} with payload {payload} did not return 400 (returned {res.status_code})"
            )
            data = res.get_json()
            self.assertIsNotNone(data, f"{method} {path} did not return JSON body")
            self.assertEqual(
                data.get("status"), "INVALID_INPUT",
                f"{method} {path} returned status '{data.get('status')}', expected 'INVALID_INPUT'"
            )

    def test_02_verify_api_404_responses(self):
        """404 endpoints must return structured JSON status='NOT_FOUND'."""
        endpoints = [
            "/api/sessions/nonexistent-session-id/state",
            "/api/sessions/nonexistent-session-id/repair-plan",
            "/api/sessions/nonexistent-session-id/audit/verify",
        ]
        for ep in endpoints:
            res = self.client.get(ep)
            self.assertEqual(res.status_code, 404, f"{ep} did not return 404")
            data = res.get_json()
            self.assertEqual(data.get("status"), "NOT_FOUND", f"{ep} status was {data.get('status')}")

    def test_03_verify_api_422_responses(self):
        """Uncalibrated mat or indeterminate instrument evidence returns 422 INDETERMINATE."""
        # 1. Blank calibration image
        blank = np.ones((400, 400, 3), dtype=np.uint8) * 255
        _, buf = cv2.imencode(".jpg", blank)
        res = self.client.post("/api/calibration", data={"image": (io.BytesIO(buf.tobytes()), "c.jpg")}, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.get_json().get("status"), "INDETERMINATE")

        # 2. Negative continuity evidence
        sid = self.client.post("/api/sessions", json={"preset_id": "led_blink"}).get_json()["session_id"]
        res_ev = self.client.post(f"/api/sessions/{sid}/instruments/evidence", json={"kind": "continuity", "from": "a", "to": "b", "connected": False})
        self.assertEqual(res_ev.status_code, 422)
        self.assertEqual(res_ev.get_json().get("status"), "INDETERMINATE")


class TestDetectorAssertionsAdversarial(unittest.TestCase):
    """Verify that detector calculations, mathematical formulas, and translations are strictly asserted."""

    def test_01_resistor_color_calculation_strict_math(self):
        """Assert exact digit, multiplier, and tolerance values in resistor decoding."""
        decoder = ResistorDecoder()

        # Check standard definitions
        self.assertEqual(COLOR_DIGITS["red"], 2)
        self.assertEqual(COLOR_DIGITS["brown"], 1)
        self.assertEqual(COLOR_MULTIPLIERS["brown"], 10)
        self.assertEqual(COLOR_MULTIPLIERS["red"], 100)
        self.assertEqual(COLOR_TOLERANCES["gold"], "5%")

        # Math test: Red (2), Violet (7), Orange (10^3 = 1000), Gold (5%) -> 27k ohm
        # Let's test snap_to_e12 and format_ohms
        ohms = 27 * 1000  # 27000
        snapped = snap_to_e12(ohms)
        self.assertEqual(snapped, 27000)
        fmt, raw = format_ohms(snapped, "5%")
        self.assertEqual(fmt, "27k 5%")
        self.assertEqual(raw, "27k")

    def test_02_wire_endpoint_coordinate_geometry(self):
        """Assert WireTracer endpoint extraction geometry on horizontal and vertical lines."""
        # Horizontal wire from (10, 50) to (90, 50)
        frame_h = np.full((100, 100, 3), 128, dtype=np.uint8)
        cv2.line(frame_h, (10, 50), (90, 50), (0, 0, 255), thickness=3)
        ep1, ep2 = WireTracer.get_endpoints(frame_h, {"x1": 5, "y1": 45, "x2": 95, "y2": 55})
        self.assertIsNotNone(ep1)
        self.assertIsNotNone(ep2)
        xs = sorted([ep1[0], ep2[0]])
        ys = sorted([ep1[1], ep2[1]])
        self.assertAlmostEqual(xs[0], 10, delta=4)
        self.assertAlmostEqual(xs[1], 90, delta=4)
        self.assertAlmostEqual(ys[0], 50, delta=3)
        self.assertAlmostEqual(ys[1], 50, delta=3)

    def test_03_tracker_ema_exact_coordinate_formula(self):
        """Assert Tracker coordinate EMA formula: new_coord = int(alpha * det + (1-alpha) * track)."""
        alpha = 0.65
        tracker = Tracker(alpha=alpha, iou_thresh=0.38, max_missing=3)

        box_0 = {"class": "led", "confidence": 0.80, "bbox": {"x1": 100, "y1": 100, "x2": 200, "y2": 200}}
        tracker.update([box_0])

        box_1 = {"class": "led", "confidence": 0.90, "bbox": {"x1": 110, "y1": 120, "x2": 210, "y2": 220}}
        out = tracker.update([box_1])

        expected_x1 = int(0.65 * 110 + 0.35 * 100)  # 71.5 + 35 = 106.5 -> 106
        expected_y1 = int(0.65 * 120 + 0.35 * 100)  # 78.0 + 35 = 113.0 -> 113
        expected_x2 = int(0.65 * 210 + 0.35 * 200)  # 136.5 + 70 = 206.5 -> 206
        expected_y2 = int(0.65 * 220 + 0.35 * 200)  # 143.0 + 70 = 213.0 -> 213
        expected_conf = round(0.7 * 0.90 + 0.3 * 0.80, 3)  # 0.63 + 0.24 = 0.87

        self.assertEqual(out[0]["bbox"]["x1"], expected_x1)
        self.assertEqual(out[0]["bbox"]["y1"], expected_y1)
        self.assertEqual(out[0]["bbox"]["x2"], expected_x2)
        self.assertEqual(out[0]["bbox"]["y2"], expected_y2)
        self.assertEqual(out[0]["confidence"], expected_conf)

    def test_04_zoom_coordinate_translation_math(self):
        """Assert AutoZoom translations: det_x - crop_x1, det_y - crop_y1."""
        frame = np.zeros((600, 800, 3), dtype=np.uint8)
        az = AutoZoom(alpha=0.5, margin=0.2)

        # Breadboard: x1=200, y1=150, x2=600, y2=450 (w=400, h=300)
        # Margin: mw = 400 * 0.2 = 80, mh = 300 * 0.2 = 60
        # Target crop: [200-80, 150-60, 600+80, 450+60] = [120, 90, 680, 510]
        # First frame with alpha=0.5: current_crop starts at None, sets directly to target!
        bb_detection = [{"class": "breadboard", "bbox": {"x1": 200, "y1": 150, "x2": 600, "y2": 450}}]
        wire_detection = {
            "class": "wire",
            "bbox": {"x1": 250, "y1": 200, "x2": 350, "y2": 300},
            "endpoints": [[255, 205], [345, 295]]
        }
        cropped, trans = az.process(frame, bb_detection + [wire_detection])

        self.assertEqual(az.current_crop, [120, 90, 680, 510])
        # Wire translated: x - 120, y - 90
        wire_trans = next(d for d in trans if d["class"] == "wire")
        self.assertEqual(wire_trans["bbox"], {"x1": 250 - 120, "y1": 200 - 90, "x2": 350 - 120, "y2": 300 - 90})
        self.assertEqual(wire_trans["endpoints"], [[255 - 120, 205 - 90], [345 - 120, 295 - 90]])


if __name__ == "__main__":
    unittest.main()
