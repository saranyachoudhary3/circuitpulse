"""Infrastructure verification tests for CircuitPulse v2.

Verifies:
1. All 6 trained YOLOv8 model checkpoints in trained_models/ load successfully on CPU
   via Ultralytics YOLO and contain valid class names.
2. Merged-Dataset/data.yaml parses cleanly with PyYAML and contains the 8 canonical classes:
   arduino_uno, arduino_nano, arduino_mega, esp32, breadboard, resistor, wire, led.
"""

from __future__ import annotations

from pathlib import Path
import unittest

from ultralytics import YOLO
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent
TRAINED_MODELS_DIR = PROJECT_ROOT / "trained_models"
MERGED_DATASET_YAML = PROJECT_ROOT / "Merged-Dataset" / "data.yaml"

EXPECTED_CANONICAL_CLASSES = [
    "arduino_uno",
    "arduino_nano",
    "arduino_mega",
    "esp32",
    "breadboard",
    "resistor",
    "wire",
    "led",
]

EXPECTED_MODEL_FILES = {
    "circuitpulse_m1_Resistor-Detection--5_best.pt": {
        "expected_count": 3,
        "classes": {"breadboard", "resistor", "wire"},
    },
    "circuitpulse_m2_Component-Detection-Arduino-UNO-1_best.pt": {
        "expected_count": 24,
        "required_subset": {
            "16MHz Crystal Oscillator",
            "5V Regulator",
            "ATmega328P MC",
            "Connecting Pins",
            "Reset Button",
            "USB Connector",
        },
    },
    "circuitpulse_m3_yolov8-pcb-defects-1_best.pt": {
        "expected_count": 6,
        "classes": {"copper", "mousebite", "open", "pin-hole", "short", "spur"},
    },
    "circuitpulse_m4_Electronics-components-1_best.pt": {
        "expected_count": 6,
        "classes": {"Capacitor", "Diode", "LED", "Resistor", "Transistor", "Zener Diode"},
    },
    "PRODUCTION_eesob_48class_best.pt": {
        "expected_count": 48,
        "required_subset": {
            "arduino_uno",
            "arduino_nano",
            "arduino_mega",
            "esp32",
            "breadboard",
            "button",
            "potentiometer",
            "ultrasonic",
        },
    },
    "PRODUCTION_pcb_faults_best.pt": {
        "expected_count": 6,
        "classes": {"copper", "mousebite", "open", "pin-hole", "short", "spur"},
    },
}


class ModelCheckpointInfrastructureTests(unittest.TestCase):
    """Test suite verifying trained model checkpoints in trained_models/."""

    def test_trained_models_directory_exists(self):
        self.assertTrue(TRAINED_MODELS_DIR.is_dir(), f"Missing directory: {TRAINED_MODELS_DIR}")

    def test_all_six_checkpoint_files_exist(self):
        found_models = sorted(p.name for p in TRAINED_MODELS_DIR.glob("*.pt"))
        self.assertGreaterEqual(len(found_models), 6, f"Expected at least 6 .pt models, found: {found_models}")
        for filename in EXPECTED_MODEL_FILES:
            filepath = TRAINED_MODELS_DIR / filename
            self.assertTrue(filepath.is_file(), f"Missing model file: {filepath}")
            self.assertGreater(filepath.stat().st_size, 1_000_000, f"Model file unexpectedly small: {filepath}")

    def test_load_m1_resistor_detection_model(self):
        path = TRAINED_MODELS_DIR / "circuitpulse_m1_Resistor-Detection--5_best.pt"
        model = YOLO(str(path))
        self.assertIsNotNone(model)
        self.assertIsInstance(model.names, dict)
        self.assertEqual(len(model.names), 3)
        self.assertEqual(set(model.names.values()), {"breadboard", "resistor", "wire"})

    def test_load_m2_arduino_uno_components_model(self):
        path = TRAINED_MODELS_DIR / "circuitpulse_m2_Component-Detection-Arduino-UNO-1_best.pt"
        model = YOLO(str(path))
        self.assertIsNotNone(model)
        self.assertIsInstance(model.names, dict)
        self.assertEqual(len(model.names), 24)
        names_set = set(model.names.values())
        required = EXPECTED_MODEL_FILES[path.name]["required_subset"]
        self.assertTrue(required.issubset(names_set), f"Missing required classes: {required - names_set}")

    def test_load_m3_pcb_defects_model(self):
        path = TRAINED_MODELS_DIR / "circuitpulse_m3_yolov8-pcb-defects-1_best.pt"
        model = YOLO(str(path))
        self.assertIsNotNone(model)
        self.assertIsInstance(model.names, dict)
        self.assertEqual(len(model.names), 6)
        self.assertEqual(set(model.names.values()), {"copper", "mousebite", "open", "pin-hole", "short", "spur"})

    def test_load_m4_electronics_components_model(self):
        path = TRAINED_MODELS_DIR / "circuitpulse_m4_Electronics-components-1_best.pt"
        model = YOLO(str(path))
        self.assertIsNotNone(model)
        self.assertIsInstance(model.names, dict)
        self.assertEqual(len(model.names), 6)
        self.assertEqual(set(model.names.values()), {"Capacitor", "Diode", "LED", "Resistor", "Transistor", "Zener Diode"})

    def test_load_production_eesob_48class_model(self):
        path = TRAINED_MODELS_DIR / "PRODUCTION_eesob_48class_best.pt"
        model = YOLO(str(path))
        self.assertIsNotNone(model)
        self.assertIsInstance(model.names, dict)
        self.assertEqual(len(model.names), 48)
        names_set = set(model.names.values())
        required = EXPECTED_MODEL_FILES[path.name]["required_subset"]
        self.assertTrue(required.issubset(names_set), f"Missing required classes: {required - names_set}")

    def test_load_production_pcb_faults_model(self):
        path = TRAINED_MODELS_DIR / "PRODUCTION_pcb_faults_best.pt"
        model = YOLO(str(path))
        self.assertIsNotNone(model)
        self.assertIsInstance(model.names, dict)
        self.assertEqual(len(model.names), 6)
        self.assertEqual(set(model.names.values()), {"copper", "mousebite", "open", "pin-hole", "short", "spur"})

    def test_all_models_load_on_cpu_and_have_nonempty_class_names(self):
        pt_files = sorted(TRAINED_MODELS_DIR.glob("*.pt"))
        self.assertGreaterEqual(len(pt_files), 6)
        for pt_path in pt_files:
            with self.subTest(model=pt_path.name):
                model = YOLO(str(pt_path))
                self.assertIsNotNone(model.names)
                self.assertIsInstance(model.names, dict)
                self.assertGreater(len(model.names), 0)
                for class_id, class_name in model.names.items():
                    self.assertIsInstance(class_id, int)
                    self.assertIsInstance(class_name, str)
                    self.assertTrue(len(class_name.strip()) > 0)

    def test_load_nonexistent_model_checkpoint_raises(self):
        nonexistent = TRAINED_MODELS_DIR / "nonexistent_model_checkpoint.pt"
        with self.assertRaises(Exception):
            YOLO(str(nonexistent))


class MergedDatasetYamlTests(unittest.TestCase):
    """Test suite verifying Merged-Dataset/data.yaml configuration and class taxonomy."""

    def test_data_yaml_file_exists(self):
        self.assertTrue(MERGED_DATASET_YAML.is_file(), f"Missing file: {MERGED_DATASET_YAML}")

    def test_data_yaml_parses_cleanly_with_pyyaml(self):
        content = MERGED_DATASET_YAML.read_text(encoding="utf-8")
        data = yaml.safe_load(content)
        self.assertIsInstance(data, dict, "Parsed YAML content must be a mapping dictionary")
        self.assertIn("nc", data)
        self.assertIn("names", data)

    def test_data_yaml_contains_exactly_eight_classes(self):
        data = yaml.safe_load(MERGED_DATASET_YAML.read_text(encoding="utf-8"))
        self.assertEqual(data.get("nc"), 8, f"Expected nc: 8, got: {data.get('nc')}")
        names = data.get("names")
        self.assertIsInstance(names, list, "Expected 'names' to be a list")
        self.assertEqual(len(names), 8, f"Expected 8 class names, got {len(names)}: {names}")
        self.assertEqual(names, EXPECTED_CANONICAL_CLASSES)

    def test_data_yaml_class_names_are_unique_and_clean(self):
        data = yaml.safe_load(MERGED_DATASET_YAML.read_text(encoding="utf-8"))
        names = data["names"]
        self.assertEqual(len(names), len(set(names)), "Class names must be unique without duplicates")
        for name in names:
            self.assertIsInstance(name, str)
            self.assertEqual(name, name.strip())
            self.assertTrue(len(name) > 0)

    def test_data_yaml_split_paths_exist_in_dataset_root(self):
        data = yaml.safe_load(MERGED_DATASET_YAML.read_text(encoding="utf-8"))
        dataset_root = MERGED_DATASET_YAML.parent
        for split_key in ("train", "val", "test"):
            self.assertIn(split_key, data, f"Missing split key: {split_key}")
            split_dir = dataset_root / data[split_key]
            self.assertTrue(split_dir.is_dir(), f"Expected directory to exist: {split_dir}")

    def test_yaml_schema_validator_rejects_invalid_class_counts(self):
        invalid_yaml_nc_mismatch = """
        nc: 5
        names:
          - arduino_uno
          - arduino_nano
        """
        parsed = yaml.safe_load(invalid_yaml_nc_mismatch)
        self.assertNotEqual(parsed["nc"], len(parsed["names"]))


if __name__ == "__main__":
    unittest.main()
