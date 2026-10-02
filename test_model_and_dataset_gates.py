import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from logic.dataset_manifest import DatasetManifestError, load_and_validate, summary
from tools.write_engine_manifest import build_manifest
from vision.model_manifest import ModelManifestError, validate_engine


CAPABILITIES = ["component_detection", "wire_instance_segmentation", "terminal_localization"]


class ModelAndDatasetGateTests(unittest.TestCase):
    def test_engine_manifest_written_by_tool_meets_runtime_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Path(directory) / "scene.engine"
            engine.write_bytes(b"verified-test-engine")
            manifest = build_manifest(engine, "RTX 5050", 12.5, 0, ["wire"], CAPABILITIES)
            path = engine.with_suffix(".manifest.json")
            path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertEqual(validate_engine(engine, path)["engine_sha256"], hashlib.sha256(engine.read_bytes()).hexdigest())

    def test_engine_manifest_rejects_missing_automatic_mapping_capability(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Path(directory) / "scene.engine"
            engine.write_bytes(b"test")
            with self.assertRaises(ModelManifestError):
                build_manifest(engine, "RTX 5050", 12.5, 0, ["wire"], ["component_detection"])

    def test_dataset_validator_requires_session_disjoint_splits(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "dataset.json"
            data = json.loads((Path(__file__).parent / "benchmarks" / "dataset_manifest.example.json").read_text(encoding="utf-8"))
            for split, records in data["splits"].items():
                record = records[0]
                record["sample_id"] = f"real-{split}-001"
                for kind in ("frame", "annotation"):
                    path = Path(directory) / record[f"{kind}_path"]
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(f"real-{split}-{kind}", encoding="utf-8")
                    record[f"{kind}_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            manifest.write_text(json.dumps(data), encoding="utf-8")
            payload = load_and_validate(manifest, {"arduino_d13_led"})
            self.assertEqual(summary(payload)["split_sample_counts"]["test"], 1)
            data["splits"]["test"][0]["assembly_session_id"] = "assembly-a"
            manifest.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(DatasetManifestError):
                load_and_validate(manifest)
