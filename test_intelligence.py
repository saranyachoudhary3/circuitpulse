import tempfile
import unittest
import numpy as np
import json
from pathlib import Path

from logic.benchmark import replay_suite
from logic.audit import SessionAuditLog
from logic.bridge import VisionGraphBridge
from logic.catalog import ComponentCatalog, PresetCatalog
from logic.eda import import_kicad_legacy_netlist, import_spice_netlist
from logic.digital_twin import DigitalTwinEngine
from logic.firmware import analyze_firmware, verify_firmware_against_preset
from logic.instruments import InstrumentRegistry
from logic.readiness import automatic_verification_readiness
from logic.session import GraphSession, SessionManager
from vision.calibration import CalibrationMat, CalibrationState
from vision.layout_measurement import LayoutMeasurementError, build_layout_candidate
from vision.evidence_contract import VisionEvidenceError, VisionEvidenceValidator
from vision.wire_masks import WireMaskExtractor


ROOT = Path(__file__).parent


class IntelligenceLayerTests(unittest.TestCase):
    def test_calibrated_bridge_fuses_endpoint_candidates(self):
        session = GraphSession(PresetCatalog().get("led_blink"))
        bridge = VisionGraphBridge()
        terminals = [{"id": "arduino:D13", "x": 0, "y": 0}, {"id": "bb:r7a", "x": 10, "y": 0}]
        for _ in range(5):
            state = bridge.observe(session, terminals, [{"id": "w1", "wire_color": "yellow", "endpoints": [[0, 0], [10, 0]]}])
        self.assertIn("arduino:D13 <-> bb:r7a", {edge["id"] for edge in state["graph"]["observed"]})

    def test_bridge_keeps_unknown_endpoint_ambiguous(self):
        session = GraphSession(PresetCatalog().get("led_blink"))
        state = VisionGraphBridge().observe(session, [{"id": "arduino:D13", "x": 0, "y": 0}], [{"id": "w1", "endpoints": [[0, 0], [50, 50]]}])
        self.assertTrue(state["vision_ambiguities"])
        self.assertEqual(state["status"], "INCOMPLETE")

    def test_firmware_detects_i2c_and_output_conflict(self):
        analysis = analyze_firmware("pinMode(D13, INPUT); Wire.begin();")
        self.assertTrue(analysis["protocols"]["i2c"])
        findings = verify_firmware_against_preset(analysis, PresetCatalog().get("led_blink"))
        self.assertIn("FIRMWARE_PIN_MODE_CONFLICT", {item["code"] for item in findings})

    def test_spice_import_exposes_component_net_graph(self):
        imported = import_spice_netlist("V1 VCC 0 DC 5\nR1 VCC LED_A 220\n")
        self.assertEqual(len(imported["components"]), 2)
        self.assertTrue(imported["connections"])

    def test_kicad_legacy_import_exposes_net(self):
        text = '(net (code 1) (name "GND") (node (ref "D1") (pin "2")) (node (ref "J1") (pin "1")))'
        imported = import_kicad_legacy_netlist(text)
        self.assertEqual(imported["nets"][0]["name"], "GND")

    def test_instrument_evidence_is_normalized(self):
        evidence = InstrumentRegistry().normalize({"kind": "continuity", "from": "arduino:GND", "to": "sensor:GND", "connected": True})
        self.assertEqual(evidence["source"], "instrumented")

    def test_instrumented_continuity_promotes_a_graph_edge(self):
        session = GraphSession(PresetCatalog().get("led_blink"))
        state = session.add_instrumented_connection("arduino:D13", "bb:r7a", "continuity_probe", "yellow")
        edge = next(item for item in state["graph"]["observed"] if item["id"] == "arduino:D13 <-> bb:r7a")
        self.assertEqual(edge["source"], "instrumented")

    def test_digital_twin_rejects_unsafe_voltage_and_inductive_load(self):
        result = DigitalTwinEngine().evaluate([
            {"id": "rfid", "module_id": "rc522", "supply_voltage": 5},
            {"id": "relay", "module_id": "relay_1ch", "supply_voltage": 5, "external_inductive_load": True, "flyback_protection": False},
        ])
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual({item["code"] for item in result["findings"]}, {"VOLTAGE_INCOMPATIBLE", "FLYBACK_PROTECTION_MISSING"})

    def test_benchmark_suite_has_zero_false_safe_fixture_result(self):
        result = replay_suite(ROOT / "benchmarks" / "fixtures")
        self.assertTrue(result["development_ready"])
        self.assertFalse(result["release_ready"])
        self.assertEqual(result["false_safe_count"], 0)
        self.assertIn("i2c_sensor", result["coverage"]["missing_presets"])
        self.assertEqual(result["coverage"]["by_preset"]["led_blink"]["development_positive"], 1)

    def test_release_fixture_requires_physical_capture_provenance(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "fixture.json"
            path.write_text(json.dumps({"preset_id": "led_blink", "expected_status": "FAULT",
                                        "evidence": {"class": "held_out_physical", "capture_session_id": "rig-01", "operator": "lab"}}), encoding="utf-8")
            from logic.benchmark import BenchmarkError, replay_fixture
            with self.assertRaises(BenchmarkError):
                replay_fixture(path)

    def test_release_fixture_rejects_capture_checksum_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "capture.mp4").write_bytes(b"real recorded fixture")
            path = root / "fixture.json"
            path.write_text(json.dumps({"preset_id": "led_blink", "expected_status": "FAULT",
                                        "evidence": {"class": "held_out_physical", "capture_session_id": "rig-01", "operator": "lab",
                                                     "capture_path": "capture.mp4", "capture_sha256": "0" * 64}}), encoding="utf-8")
            from logic.benchmark import BenchmarkError, replay_fixture
            with self.assertRaises(BenchmarkError):
                replay_fixture(path)

    def test_physical_fault_fixture_requires_a_fault_class(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "capture.mp4"
            artifact.write_bytes(b"real recorded fixture")
            import hashlib
            path = root / "fixture.json"
            path.write_text(json.dumps({"preset_id": "led_blink", "expected_status": "FAULT",
                                        "evidence": {"class": "held_out_physical", "capture_session_id": "rig-01", "operator": "lab",
                                                     "capture_path": "capture.mp4", "capture_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}}), encoding="utf-8")
            from logic.benchmark import BenchmarkError, replay_fixture
            with self.assertRaises(BenchmarkError):
                replay_fixture(path)

    def test_wire_mask_extracts_two_endpoints(self):
        mask = np.zeros((32, 64), dtype=np.uint8)
        mask[16, 8:56] = 255
        result = WireMaskExtractor().extract(mask)
        self.assertEqual(result["status"], "CANDIDATE")
        self.assertEqual(len(result["endpoints"]), 2)

    def test_mask_bridge_projects_pixels_before_fusing(self):
        session = GraphSession(PresetCatalog().get("led_blink"))
        calibration = CalibrationMat()
        calibration.state = CalibrationState(
            homography=[[1, 0, 0], [0, 1, 0], [0, 0, 1]], marker_ids=[0, 1, 2, 3], frame_size=(256, 32), reprojection_error=0.0
        )
        mask = np.zeros((32, 256), dtype=np.uint8)
        mask[16, 8:240] = 255
        terminals = [{"id": "arduino:D13", "x": 8, "y": 16}, {"id": "bb:r7a", "x": 239, "y": 16}]
        bridge = VisionGraphBridge()
        for _ in range(5):
            state = bridge.observe_masks(session, calibration, terminals, [{"id": "yellow", "wire_color": "yellow", "mask": mask}])
        self.assertIn("arduino:D13 <-> bb:r7a", {edge["id"] for edge in state["graph"]["observed"]})

    def test_terminal_layout_candidate_uses_calibrated_coordinates(self):
        module = {"id": "demo", "pins": [{"name": "VCC"}, {"name": "GND"}]}
        calibration = {"homography": [[1, 0, 10], [0, 1, 20], [0, 0, 1]], "marker_ids": [0, 1, 2, 3], "frame_size": [100, 100]}
        candidate = build_layout_candidate(module, [[1, 2], [3, 4]], calibration)
        self.assertEqual(candidate["status"], "candidate")
        self.assertEqual(candidate["terminals"], [{"pin": "VCC", "x_mm": 11.0, "y_mm": 22.0}, {"pin": "GND", "x_mm": 13.0, "y_mm": 24.0}])
        with self.assertRaises(LayoutMeasurementError):
            build_layout_candidate(module, [[1, 2]], calibration)

    def test_automatic_vision_requires_model_calibration_and_reviewed_layout(self):
        with tempfile.TemporaryDirectory() as temporary:
            catalog_path = Path(temporary) / "catalog.json"
            catalog_path.write_text(json.dumps({"schema_version": 1, "modules": [{
                "id": "demo", "display_name": "Demo", "fiducial_id": "CP-DEMO", "voltage": ["5V"],
                "pins": [{"name": "P1", "role": "gpio"}, {"name": "P2", "role": "gpio"}],
                "terminal_layout": {"status": "reviewed", "terminals": [
                    {"pin": "P1", "x_mm": 1, "y_mm": 1}, {"pin": "P2", "x_mm": 2, "y_mm": 1}
                ], "coordinate_system": "calibration_mat_mm", "calibration_id": "a" * 64,
                    "review": {"reviewed_by": "test", "reviewed_at": "2026-10-02T00:00:00Z", "candidate_sha256": "b" * 64}}
            }]}), encoding="utf-8")
            calibration = CalibrationState([[1, 0, 0], [0, 1, 0], [0, 0, 1]], [0, 1, 2, 3], (100, 100), 0)
            payload = {"contract_version": 1, "model_artifact_id": "engine-sha", "calibration_id": calibration.calibration_id(),
                       "terminals": [{"id": "demo:P1", "module_id": "demo", "pin": "P1", "x": 1, "y": 1},
                                     {"id": "demo:P2", "module_id": "demo", "pin": "P2", "x": 2, "y": 1}],
                       "wires": [{"id": "w1", "endpoints": [[1, 1], [2, 1]], "confidence": 0.99}]}
            validator = VisionEvidenceValidator(ComponentCatalog(catalog_path))
            accepted = validator.validate(payload, calibration, True, "engine-sha")
            self.assertEqual(len(accepted["terminals"]), 2)
            with self.assertRaises(VisionEvidenceError):
                validator.validate(payload, calibration, False, "engine-sha")
            payload["calibration_id"] = "wrong"
            with self.assertRaises(VisionEvidenceError):
                validator.validate(payload, calibration, True, "engine-sha")

    def test_readiness_reports_all_automatic_verification_blockers(self):
        result = automatic_verification_readiness(
            camera_connected=False, model_verified=False, model_artifact_id=None,
            calibration_health={"status": "BLOCKED", "reason": "Calibration has not been completed."},
            components=ComponentCatalog(), presets=PresetCatalog(), preset_id="i2c_sensor",
        )
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual({blocker["code"] for blocker in result["blockers"]},
                         {"CAMERA_UNAVAILABLE", "MODEL_UNVERIFIED", "CALIBRATION_UNREADY", "TERMINAL_LAYOUT_UNREVIEWED"})

    def test_audit_log_hash_chain_records_session_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            log = SessionAuditLog(Path(temporary))
            manager = SessionManager(PresetCatalog(), audit_log=log)
            state = manager.create("led_blink")
            manager.get(state["session_id"]).confirm("arduino:D13", "bb:r7a", True, "yellow")
            verified = manager.verify_audit(state["session_id"])
            self.assertEqual(verified["status"], "PASS")
            self.assertGreaterEqual(verified["records"], 2)

    def test_audit_log_detects_tampered_sequence_or_payload(self):
        with tempfile.TemporaryDirectory() as temporary:
            log = SessionAuditLog(Path(temporary))
            manager = SessionManager(PresetCatalog(), audit_log=log)
            state = manager.create("led_blink")
            path = Path(temporary) / f"{state['session_id']}.jsonl"
            path.write_text(path.read_text(encoding="utf-8").replace('"sequence":1', '"sequence":7'), encoding="utf-8")
            self.assertEqual(log.verify(state["session_id"])["status"], "INVALID")


if __name__ == "__main__":
    unittest.main()
