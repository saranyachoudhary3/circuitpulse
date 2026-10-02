import unittest
import tempfile
import json
import shutil
from pathlib import Path

from logic.readiness import automatic_verification_readiness
from logic.catalog import ComponentCatalog, PresetCatalog

class ReadinessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp()
        cls.temp_path = Path(cls.temp_dir)
        
        # Write component catalog
        cls.comp_path = cls.temp_path / "catalog.json"
        comp_data = {
            "schema_version": 1,
            "modules": [
                {
                    "id": "mod1",
                    "fiducial_id": "f1",
                    "display_name": "Module 1",
                    "voltage": "3.3V",
                    "pins": [{"name": "A"}],
                    "terminal_layout": {
                        "status": "reviewed",
                        "review": {
                            "reviewed_by": "ayushman",
                            "reviewed_at": "now",
                            "candidate_sha256": "0" * 64
                        },
                        "calibration_id": "1" * 64,
                        "coordinate_system": "calibration_mat_mm",
                        "terminals": [
                            {"pin": "A", "x_mm": 0.0, "y_mm": 0.0}
                        ]
                    }
                }
            ]
        }
        cls.comp_path.write_text(json.dumps(comp_data), encoding="utf-8")
        
        # Write preset catalog
        cls.preset_dir = cls.temp_path / "presets"
        cls.preset_dir.mkdir()
        preset_data = {
            "schema_version": 1,
            "id": "preset1",
            "name": "Preset 1",
            "description": "Desc",
            "required_components": ["mod1"],
            "connections": [{"id": "conn1", "from": "mod1.A", "to": "mod1.A"}]
        }
        (cls.preset_dir / "preset1.json").write_text(json.dumps(preset_data), encoding="utf-8")
        
        cls.components = ComponentCatalog(path=cls.comp_path)
        cls.presets = PresetCatalog(directory=cls.preset_dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir)

    def test_all_systems_ready_returns_ready(self):
        result = automatic_verification_readiness(
            camera_connected=True,
            model_verified=True,
            model_artifact_id="art1",
            calibration_health={"status": "READY"},
            components=self.components,
            presets=self.presets,
            preset_id="preset1"
        )
        self.assertEqual(result["status"], "READY")
        self.assertTrue(result["automatic_verification"])
        self.assertEqual(result["blockers"], [])
        self.assertEqual(result["preset"]["id"], "preset1")

    def test_camera_unavailable_blocks(self):
        result = automatic_verification_readiness(
            camera_connected=False,
            model_verified=True,
            model_artifact_id="art1",
            calibration_health={"status": "READY"},
            components=self.components,
            presets=self.presets,
            preset_id="preset1"
        )
        blocker_codes = [b["code"] for b in result["blockers"]]
        self.assertIn("CAMERA_UNAVAILABLE", blocker_codes)
        self.assertEqual(result["status"], "BLOCKED")

    def test_model_unverified_blocks(self):
        result = automatic_verification_readiness(
            camera_connected=True,
            model_verified=False,
            model_artifact_id="art1",
            calibration_health={"status": "READY"},
            components=self.components,
            presets=self.presets,
            preset_id="preset1"
        )
        blocker_codes = [b["code"] for b in result["blockers"]]
        self.assertIn("MODEL_UNVERIFIED", blocker_codes)

    def test_model_missing_artifact_id_blocks(self):
        result = automatic_verification_readiness(
            camera_connected=True,
            model_verified=True,
            model_artifact_id=None,
            calibration_health={"status": "READY"},
            components=self.components,
            presets=self.presets,
            preset_id="preset1"
        )
        blocker_codes = [b["code"] for b in result["blockers"]]
        self.assertIn("MODEL_UNVERIFIED", blocker_codes)

    def test_calibration_not_ready_blocks(self):
        result = automatic_verification_readiness(
            camera_connected=True,
            model_verified=True,
            model_artifact_id="art1",
            calibration_health={"status": "ERROR", "reason": "Bad"},
            components=self.components,
            presets=self.presets,
            preset_id="preset1"
        )
        blocker_codes = [b["code"] for b in result["blockers"]]
        self.assertIn("CALIBRATION_UNREADY", blocker_codes)
        
    def test_multiple_blockers_accumulate(self):
        result = automatic_verification_readiness(
            camera_connected=False,
            model_verified=False,
            model_artifact_id=None,
            calibration_health={"status": "ERROR"},
            components=self.components,
            presets=self.presets,
            preset_id="preset1"
        )
        self.assertEqual(len(result["blockers"]), 3)

    def test_preset_without_id_returns_none_preset(self):
        result = automatic_verification_readiness(
            camera_connected=True,
            model_verified=True,
            model_artifact_id="art1",
            calibration_health={"status": "READY"},
            components=self.components,
            presets=self.presets,
            preset_id=None
        )
        self.assertIsNone(result["preset"])
        self.assertEqual(result["status"], "READY")

    def test_blocked_status_when_any_blocker_exists(self):
        result = automatic_verification_readiness(
            camera_connected=False,
            model_verified=True,
            model_artifact_id="art1",
            calibration_health={"status": "READY"},
            components=self.components,
            presets=self.presets,
            preset_id="preset1"
        )
        self.assertEqual(result["status"], "BLOCKED")
        self.assertFalse(result["automatic_verification"])
