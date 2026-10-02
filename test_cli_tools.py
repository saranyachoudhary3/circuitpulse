"""Unit and integration tests for all 7 CLI tools in tools/.

Tests:
1. tools/generate_fiducials.py
2. tools/import_logic_trace.py
3. tools/import_voltage_trace.py
4. tools/measure_terminal_layout.py
5. tools/review_terminal_layout.py
6. tools/validate_dataset_manifest.py
7. tools/write_engine_manifest.py

Tests verify argument parsing, exit codes, output files, schema compliance,
and error handling for both valid and invalid arguments.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from logic.dataset_manifest import REQUIRED_ANNOTATIONS
from vision.fiducials import MODULE_MARKER_IDS

PROJECT_ROOT = Path(__file__).resolve().parent
TOOLS_DIR = PROJECT_ROOT / "tools"


import os

def run_cli_tool(tool_name: str, args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Execute a CLI tool script via subprocess and return completed process."""
    script_path = TOOLS_DIR / tool_name
    command = [sys.executable, str(script_path)] + args
    env = dict(os.environ)
    env["PYTHONPATH"] = str(PROJECT_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        command,
        cwd=str(cwd or PROJECT_ROOT),
        capture_output=True,
        text=True,
        env=env,
    )


class GenerateFiducialsCliTests(unittest.TestCase):
    """Test suite for tools/generate_fiducials.py."""

    def test_generate_fiducials_valid_invocation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_path = Path(temp_dir) / "fiducials"
            result = run_cli_tool("generate_fiducials.py", ["--output", str(out_path), "--pixels", "100"])
            self.assertEqual(result.returncode, 0, f"Tool failed with stderr: {result.stderr}")
            expected_total = 4 + len(MODULE_MARKER_IDS)
            self.assertIn(f"Generated {expected_total} markers in", result.stdout)

            # Verify calibration markers 0..3 exist and are non-empty PNGs
            for marker_id in range(4):
                marker_file = out_path / f"calibration_{marker_id}.png"
                self.assertTrue(marker_file.is_file(), f"Missing marker: {marker_file}")
                self.assertGreater(marker_file.stat().st_size, 0)

            # Verify module markers exist
            for marker_id, label in MODULE_MARKER_IDS.items():
                module_file = out_path / f"{marker_id}_{label}.png"
                self.assertTrue(module_file.is_file(), f"Missing module marker: {module_file}")
                self.assertGreater(module_file.stat().st_size, 0)

    def test_generate_fiducials_invalid_pixel_argument(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = run_cli_tool("generate_fiducials.py", ["--output", temp_dir, "--pixels", "not_an_int"])
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("invalid int value", result.stderr)

    def test_generate_fiducials_help_flag(self):
        result = run_cli_tool("generate_fiducials.py", ["--help"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("Generate CircuitPulse ArUco marker PNGs", result.stdout)


class ImportLogicTraceCliTests(unittest.TestCase):
    """Test suite for tools/import_logic_trace.py."""

    def _create_sample_logic_csv(self, path: Path) -> None:
        csv_content = (
            "time_s,CLK,DATA\n"
            "0.000000,0,0\n"
            "0.000001,1,0\n"
            "0.000002,1,1\n"
            "0.000003,0,1\n"
        )
        path.write_text(csv_content, encoding="utf-8")

    def test_import_logic_trace_valid_file_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "logic.csv"
            out_json = Path(temp_dir) / "trace.json"
            self._create_sample_logic_csv(csv_path)

            result = run_cli_tool(
                "import_logic_trace.py",
                [str(csv_path), "--signal", "CLK=clock_net", "--signal", "DATA=data_net", "--output", str(out_json)],
            )
            self.assertEqual(result.returncode, 0, f"Error: {result.stderr}")
            self.assertTrue(out_json.is_file())
            data = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(data.get("schema_version"), 1)
            self.assertEqual(data.get("evidence_type"), "logic_analyzer_csv")
            self.assertEqual(data.get("sample_count"), 4)
            digital_trace = data.get("measurements", {}).get("digital_trace", [])
            self.assertEqual(len(digital_trace), 4)
            self.assertEqual(digital_trace[0]["levels"], {"clock_net": 0, "data_net": 0})
            self.assertEqual(digital_trace[2]["levels"], {"clock_net": 1, "data_net": 1})

    def test_import_logic_trace_valid_stdout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "logic.csv"
            self._create_sample_logic_csv(csv_path)

            result = run_cli_tool(
                "import_logic_trace.py",
                [str(csv_path), "--signal", "CLK=clock_net", "--signal", "DATA=data_net"],
            )
            self.assertEqual(result.returncode, 0, f"Error: {result.stderr}")
            data = json.loads(result.stdout)
            self.assertEqual(data.get("evidence_type"), "logic_analyzer_csv")
            self.assertEqual(data.get("sample_count"), 4)

    def test_import_logic_trace_missing_signal_flag(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "logic.csv"
            self._create_sample_logic_csv(csv_path)

            result = run_cli_tool("import_logic_trace.py", [str(csv_path)])
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("required: --signal", result.stderr)

    def test_import_logic_trace_invalid_signal_format(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "logic.csv"
            self._create_sample_logic_csv(csv_path)

            result = run_cli_tool(
                "import_logic_trace.py",
                [str(csv_path), "--signal", "MALFORMED_NO_EQUALS"],
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Signal mappings use CSV_HEADER=REVIEWED_NET", result.stderr)

    def test_import_logic_trace_empty_signal_header_or_net(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "logic.csv"
            self._create_sample_logic_csv(csv_path)

            result = run_cli_tool(
                "import_logic_trace.py",
                [str(csv_path), "--signal", "=some_net"],
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("non-empty CSV_HEADER=REVIEWED_NET", result.stderr)

    def test_import_logic_trace_duplicate_signal_header(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "logic.csv"
            self._create_sample_logic_csv(csv_path)

            result = run_cli_tool(
                "import_logic_trace.py",
                [str(csv_path), "--signal", "CLK=clk_a", "--signal", "CLK=clk_b"],
            )
            self.assertNotEqual(result.returncode, 0)
            output = result.stderr + result.stdout
            self.assertIn("Each CSV signal header may be mapped only once", output)

    def test_import_logic_trace_missing_time_column_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "invalid.csv"
            csv_path.write_text("CLK,DATA\n0,1\n1,0\n", encoding="utf-8")

            result = run_cli_tool(
                "import_logic_trace.py",
                [str(csv_path), "--signal", "CLK=clk_net"],
            )
            self.assertNotEqual(result.returncode, 0)
            output = result.stderr + result.stdout
            self.assertIn("TRACE_NOT_READY", output)
            self.assertIn("requires one time column", output)

    def test_import_logic_trace_nonexistent_csv_file(self):
        result = run_cli_tool(
            "import_logic_trace.py",
            ["nonexistent_capture.csv", "--signal", "CLK=clk_net"],
        )
        self.assertNotEqual(result.returncode, 0)
        output = result.stderr + result.stdout
        self.assertIn("TRACE_NOT_READY", output)


class ImportVoltageTraceCliTests(unittest.TestCase):
    """Test suite for tools/import_voltage_trace.py."""

    def _create_sample_voltage_csv(self, path: Path) -> None:
        csv_content = (
            "time_s,CH1,CH2\n"
            "0.000,5.02,0.01\n"
            "0.001,4.98,0.02\n"
            "0.002,5.00,0.00\n"
        )
        path.write_text(csv_content, encoding="utf-8")

    def test_import_voltage_trace_valid_file_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "voltage.csv"
            out_json = Path(temp_dir) / "vtrace.json"
            self._create_sample_voltage_csv(csv_path)

            result = run_cli_tool(
                "import_voltage_trace.py",
                [str(csv_path), "--channel", "CH1=VCC", "--channel", "CH2=GND", "--output", str(out_json)],
            )
            self.assertEqual(result.returncode, 0, f"Error: {result.stderr}")
            self.assertTrue(out_json.is_file())
            data = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(data.get("schema_version"), 1)
            self.assertEqual(data.get("evidence_type"), "voltage_trace_csv")
            self.assertEqual(data.get("sample_count"), 3)
            samples = data.get("measurements", {}).get("voltage_trace", [])
            self.assertEqual(len(samples), 3)
            self.assertEqual(samples[0]["voltages_v"], {"VCC": 5.02, "GND": 0.01})
            self.assertEqual(samples[1]["voltages_v"], {"VCC": 4.98, "GND": 0.02})

    def test_import_voltage_trace_valid_stdout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "voltage.csv"
            self._create_sample_voltage_csv(csv_path)

            result = run_cli_tool(
                "import_voltage_trace.py",
                [str(csv_path), "--channel", "CH1=VCC", "--channel", "CH2=GND"],
            )
            self.assertEqual(result.returncode, 0, f"Error: {result.stderr}")
            data = json.loads(result.stdout)
            self.assertEqual(data.get("evidence_type"), "voltage_trace_csv")
            self.assertEqual(data.get("sample_count"), 3)

    def test_import_voltage_trace_missing_channel_flag(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "voltage.csv"
            self._create_sample_voltage_csv(csv_path)

            result = run_cli_tool("import_voltage_trace.py", [str(csv_path)])
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("required: --channel", result.stderr)

    def test_import_voltage_trace_invalid_channel_format(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "voltage.csv"
            self._create_sample_voltage_csv(csv_path)

            result = run_cli_tool(
                "import_voltage_trace.py",
                [str(csv_path), "--channel", "NO_EQUALS"],
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Channel mappings use CSV_HEADER=REVIEWED_NET", result.stderr)

    def test_import_voltage_trace_duplicate_channel_header(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "voltage.csv"
            self._create_sample_voltage_csv(csv_path)

            result = run_cli_tool(
                "import_voltage_trace.py",
                [str(csv_path), "--channel", "CH1=net_a", "--channel", "CH1=net_b"],
            )
            self.assertNotEqual(result.returncode, 0)
            output = result.stderr + result.stdout
            self.assertIn("Each CSV channel header may be mapped only once", output)

    def test_import_voltage_trace_non_numeric_voltage_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "corrupt_voltage.csv"
            csv_path.write_text("time_s,CH1\n0.000,not_a_number\n", encoding="utf-8")

            result = run_cli_tool(
                "import_voltage_trace.py",
                [str(csv_path), "--channel", "CH1=VCC"],
            )
            self.assertNotEqual(result.returncode, 0)
            output = result.stderr + result.stdout
            self.assertIn("TRACE_NOT_READY", output)
            self.assertIn("not numeric", output)

    def test_import_voltage_trace_nonexistent_csv_file(self):
        result = run_cli_tool(
            "import_voltage_trace.py",
            ["missing_scope_capture.csv", "--channel", "CH1=VCC"],
        )
        self.assertNotEqual(result.returncode, 0)
        output = result.stderr + result.stdout
        self.assertIn("TRACE_NOT_READY", output)


class MeasureTerminalLayoutCliTests(unittest.TestCase):
    """Test suite for tools/measure_terminal_layout.py."""

    def _setup_uno_measurement_files(self, temp_dir: Path) -> tuple[Path, Path]:
        cal_path = temp_dir / "calibration.json"
        cal_data = {
            "homography": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            "marker_ids": [0, 1, 2, 3],
            "calibration_id": "a" * 64,
        }
        cal_path.write_text(json.dumps(cal_data), encoding="utf-8")

        points_path = temp_dir / "points.json"
        # arduino_uno has 7 manifest pins in catalog: 5V, 3V3, GND, D13, A0, SDA, SCL
        points_data = [[10.0 + i * 5.0, 20.0] for i in range(7)]
        points_path.write_text(json.dumps(points_data), encoding="utf-8")
        return cal_path, points_path

    def test_measure_terminal_layout_valid_invocation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cal_path, points_path = self._setup_uno_measurement_files(root)
            out_json = root / "arduino_uno.candidate.json"

            result = run_cli_tool(
                "measure_terminal_layout.py",
                [
                    "--module-id", "arduino_uno",
                    "--calibration", str(cal_path),
                    "--points", str(points_path),
                    "--output", str(out_json),
                ],
            )
            self.assertEqual(result.returncode, 0, f"Error: {result.stderr}")
            self.assertIn("Wrote candidate layout for Arduino Uno", result.stdout)
            self.assertTrue(out_json.is_file())

            data = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(data.get("module_id"), "arduino_uno")
            layout = data.get("terminal_layout", {})
            self.assertEqual(layout.get("status"), "candidate")
            self.assertEqual(layout.get("coordinate_system"), "calibration_mat_mm")
            self.assertEqual(layout.get("calibration_id"), "a" * 64)
            terminals = layout.get("terminals", [])
            self.assertEqual(len(terminals), 7)
            pin_names = [t["pin"] for t in terminals]
            self.assertEqual(pin_names, ["5V", "3V3", "GND", "D13", "A0", "SDA", "SCL"])

    def test_measure_terminal_layout_unknown_module_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cal_path, points_path = self._setup_uno_measurement_files(root)

            result = run_cli_tool(
                "measure_terminal_layout.py",
                [
                    "--module-id", "non_existent_microcontroller",
                    "--calibration", str(cal_path),
                    "--points", str(points_path),
                ],
            )
            self.assertNotEqual(result.returncode, 0)
            output = result.stderr + result.stdout
            self.assertIn("Unknown module ID: non_existent_microcontroller", output)

    def test_measure_terminal_layout_pin_count_mismatch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cal_path, _ = self._setup_uno_measurement_files(root)
            bad_points = root / "bad_points.json"
            bad_points.write_text(json.dumps([[1.0, 2.0], [3.0, 4.0]]), encoding="utf-8")

            result = run_cli_tool(
                "measure_terminal_layout.py",
                [
                    "--module-id", "arduino_uno",
                    "--calibration", str(cal_path),
                    "--points", str(bad_points),
                ],
            )
            self.assertNotEqual(result.returncode, 0)
            output = result.stderr + result.stdout
            self.assertIn("Expected exactly 7 terminal points", output)

    def test_measure_terminal_layout_missing_required_args(self):
        result = run_cli_tool("measure_terminal_layout.py", ["--module-id", "arduino_uno"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("required: --calibration, --points", result.stderr)

    def test_measure_terminal_layout_invalid_calibration_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, points_path = self._setup_uno_measurement_files(root)
            corrupt_cal = root / "corrupt_cal.json"
            corrupt_cal.write_text("{{not valid json}}", encoding="utf-8")

            result = run_cli_tool(
                "measure_terminal_layout.py",
                [
                    "--module-id", "arduino_uno",
                    "--calibration", str(corrupt_cal),
                    "--points", str(points_path),
                ],
            )
            self.assertNotEqual(result.returncode, 0)
            output = result.stderr + result.stdout
            self.assertIn("Could not create candidate layout", output)


class ReviewTerminalLayoutCliTests(unittest.TestCase):
    """Test suite for tools/review_terminal_layout.py."""

    def _create_candidate_file(self, path: Path, module_id: str = "arduino_uno", spacing: float = 5.0) -> None:
        pins = ["5V", "3V3", "GND", "D13", "A0", "SDA", "SCL"]
        candidate_data = {
            "module_id": module_id,
            "terminal_layout": {
                "status": "candidate",
                "coordinate_system": "calibration_mat_mm",
                "calibration_id": "b" * 64,
                "calibration_marker_ids": [0, 1, 2, 3],
                "measurement_source": "manual_terminal_clicks",
                "terminals": [
                    {"pin": pin, "x_mm": round(10.0 + i * spacing, 3), "y_mm": 20.0}
                    for i, pin in enumerate(pins)
                ],
            },
        }
        path.write_text(json.dumps(candidate_data, indent=2), encoding="utf-8")

    def test_review_terminal_layout_valid_invocation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            candidate_path = root / "cand.json"
            reviewed_path = root / "reviewed.json"
            self._create_candidate_file(candidate_path)

            result = run_cli_tool(
                "review_terminal_layout.py",
                [
                    str(candidate_path),
                    "--reviewer", "Senior Circuit Reviewer",
                    "--output", str(reviewed_path),
                    "--minimum-spacing-mm", "0.5",
                ],
            )
            self.assertEqual(result.returncode, 0, f"Error: {result.stderr}")
            self.assertIn("Wrote reviewed terminal layout to", result.stdout)
            self.assertTrue(reviewed_path.is_file())

            data = json.loads(reviewed_path.read_text(encoding="utf-8"))
            self.assertEqual(data.get("schema_version"), 1)
            self.assertEqual(data.get("module_id"), "arduino_uno")
            layout = data.get("terminal_layout", {})
            self.assertEqual(layout.get("status"), "reviewed")
            self.assertEqual(layout.get("coordinate_system"), "calibration_mat_mm")
            self.assertEqual(layout.get("calibration_id"), "b" * 64)
            review_meta = layout.get("review", {})
            self.assertEqual(review_meta.get("reviewed_by"), "Senior Circuit Reviewer")
            self.assertEqual(review_meta.get("minimum_spacing_mm"), 0.5)
            self.assertIn("candidate_sha256", review_meta)

    def test_review_terminal_layout_missing_reviewer_flag(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            candidate_path = root / "cand.json"
            out_path = root / "out.json"
            self._create_candidate_file(candidate_path)

            result = run_cli_tool("review_terminal_layout.py", [str(candidate_path), "--output", str(out_path)])
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("required: --reviewer", result.stderr)

    def test_review_terminal_layout_terminals_too_close_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            candidate_path = root / "cand_too_close.json"
            out_path = root / "out.json"
            # Spacing of 0.1 mm with minimum spacing 0.25 mm
            self._create_candidate_file(candidate_path, spacing=0.1)

            result = run_cli_tool(
                "review_terminal_layout.py",
                [str(candidate_path), "--reviewer", "Reviewer", "--output", str(out_path), "--minimum-spacing-mm", "0.25"],
            )
            self.assertNotEqual(result.returncode, 0)
            output = result.stderr + result.stdout
            self.assertIn("LAYOUT_NOT_REVIEWED", output)
            self.assertIn("closer than", output)

    def test_review_terminal_layout_unknown_module_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            candidate_path = root / "bad_mod.json"
            out_path = root / "out.json"
            self._create_candidate_file(candidate_path, module_id="unknown_uno")

            result = run_cli_tool(
                "review_terminal_layout.py",
                [str(candidate_path), "--reviewer", "Reviewer", "--output", str(out_path)],
            )
            self.assertNotEqual(result.returncode, 0)
            output = result.stderr + result.stdout
            self.assertIn("Candidate names unknown module_id", output)

    def test_review_terminal_layout_non_candidate_status_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            candidate_path = root / "cand.json"
            out_path = root / "out.json"
            self._create_candidate_file(candidate_path)

            # Change status to already reviewed
            raw = json.loads(candidate_path.read_text(encoding="utf-8"))
            raw["terminal_layout"]["status"] = "reviewed"
            candidate_path.write_text(json.dumps(raw), encoding="utf-8")

            result = run_cli_tool(
                "review_terminal_layout.py",
                [str(candidate_path), "--reviewer", "Reviewer", "--output", str(out_path)],
            )
            self.assertNotEqual(result.returncode, 0)
            output = result.stderr + result.stdout
            self.assertIn("Only a terminal-layout candidate may be reviewed", output)

    def test_review_terminal_layout_missing_input_file(self):
        result = run_cli_tool(
            "review_terminal_layout.py",
            ["nonexistent_candidate.json", "--reviewer", "Reviewer", "--output", "out.json"],
        )
        self.assertNotEqual(result.returncode, 0)
        output = result.stderr + result.stdout
        self.assertIn("LAYOUT_NOT_REVIEWED", output)


class ValidateDatasetManifestCliTests(unittest.TestCase):
    """Test suite for tools/validate_dataset_manifest.py."""

    def _create_valid_dataset(self, root: Path, supported_presets: list[str] | None = None) -> Path:
        (root / "frames").mkdir(parents=True, exist_ok=True)
        (root / "annotations").mkdir(parents=True, exist_ok=True)

        splits = {}
        for split in ("train", "validation", "test"):
            frame_file = root / "frames" / f"{split}.png"
            ann_file = root / "annotations" / f"{split}.json"
            frame_bytes = f"frame-data-{split}".encode("utf-8")
            ann_bytes = f"ann-data-{split}".encode("utf-8")
            frame_file.write_bytes(frame_bytes)
            ann_file.write_bytes(ann_bytes)

            splits[split] = [
                {
                    "sample_id": f"sample_{split}_001",
                    "assembly_session_id": f"sess_{split}_001",
                    "frame_path": f"frames/{split}.png",
                    "annotation_path": f"annotations/{split}.json",
                    "frame_sha256": hashlib.sha256(frame_bytes).hexdigest(),
                    "annotation_sha256": hashlib.sha256(ann_bytes).hexdigest(),
                }
            ]

        manifest = {
            "schema_version": 1,
            "dataset_id": "test_circuit_dataset_v1",
            "capture_profile": {
                "camera_id": "overhead_cam_01",
                "resolution": "1920x1080",
                "fps": 30.0,
                "calibration_mat_id": "aruco_mat_v1",
                "lighting_profile": "bench_5000k_diffuse",
            },
            "annotation_coverage": sorted(list(REQUIRED_ANNOTATIONS)),
            "annotation_counts": {label: 10 for label in REQUIRED_ANNOTATIONS},
            "supported_presets": supported_presets or ["led_blink"],
            "splits": splits,
        }
        manifest_path = root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest_path

    def test_validate_dataset_manifest_valid_invocation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path = self._create_valid_dataset(root, supported_presets=["led_blink", "voltage_divider"])

            result = run_cli_tool(
                "validate_dataset_manifest.py",
                [str(manifest_path), "--require-preset", "led_blink"],
            )
            self.assertEqual(result.returncode, 0, f"Error: {result.stderr}")
            summary = json.loads(result.stdout)
            self.assertEqual(summary.get("dataset_id"), "test_circuit_dataset_v1")
            self.assertTrue(summary.get("ready_for_training"))
            self.assertEqual(summary.get("split_sample_counts"), {"train": 1, "validation": 1, "test": 1})

    def test_validate_dataset_manifest_missing_required_preset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path = self._create_valid_dataset(root, supported_presets=["led_blink"])

            result = run_cli_tool(
                "validate_dataset_manifest.py",
                [str(manifest_path), "--require-preset", "motor_driver"],
            )
            self.assertNotEqual(result.returncode, 0)
            output = result.stderr + result.stdout
            self.assertIn("DATASET_NOT_READY", output)
            self.assertIn("Dataset omits supported presets", output)

    def test_validate_dataset_manifest_leaking_assembly_session(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path = self._create_valid_dataset(root)

            # Leak train assembly_session_id into test split
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            data["splits"]["test"][0]["assembly_session_id"] = "sess_train_001"
            manifest_path.write_text(json.dumps(data), encoding="utf-8")

            result = run_cli_tool("validate_dataset_manifest.py", [str(manifest_path)])
            self.assertNotEqual(result.returncode, 0)
            output = result.stderr + result.stdout
            self.assertIn("DATASET_NOT_READY", output)
            self.assertIn("leaks from", output)
            self.assertIn("sess_train_001", output)

    def test_validate_dataset_manifest_checksum_mismatch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path = self._create_valid_dataset(root)

            # Alter frame file so sha256 no longer matches
            (root / "frames" / "train.png").write_bytes(b"altered-bytes")

            result = run_cli_tool("validate_dataset_manifest.py", [str(manifest_path)])
            self.assertNotEqual(result.returncode, 0)
            output = result.stderr + result.stdout
            self.assertIn("DATASET_NOT_READY", output)
            self.assertIn("checksum does not match the manifest", output)

    def test_validate_dataset_manifest_nonexistent_manifest(self):
        result = run_cli_tool("validate_dataset_manifest.py", ["missing_manifest.json"])
        self.assertNotEqual(result.returncode, 0)
        output = result.stderr + result.stdout
        self.assertIn("DATASET_NOT_READY", output)
        self.assertIn("Cannot load dataset manifest", output)


class WriteEngineManifestCliTests(unittest.TestCase):
    """Test suite for tools/write_engine_manifest.py."""

    def test_write_engine_manifest_valid_invocation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            engine_path = root / "detector.engine"
            engine_path.write_bytes(b"synthetic_engine_tensorrt_bytes_12345")

            result = run_cli_tool(
                "write_engine_manifest.py",
                [
                    str(engine_path),
                    "--target-gpu", "NVIDIA GeForce RTX 4090",
                    "--p95-latency-ms", "14.5",
                    "--fault-false-safe-count", "0",
                    "--classes", "breadboard", "resistor", "wire", "led",
                    "--capabilities", "component_detection", "wire_instance_segmentation", "terminal_localization",
                ],
            )
            self.assertEqual(result.returncode, 0, f"Error: {result.stderr}")
            destination = engine_path.with_suffix(".manifest.json")
            self.assertTrue(destination.is_file())
            self.assertIn(f"Wrote {destination}", result.stdout)

            manifest = json.loads(destination.read_text(encoding="utf-8"))
            self.assertEqual(manifest.get("schema_version"), 1)
            self.assertEqual(manifest.get("target_gpu"), "NVIDIA GeForce RTX 4090")
            self.assertEqual(manifest.get("engine_sha256"), hashlib.sha256(b"synthetic_engine_tensorrt_bytes_12345").hexdigest())
            self.assertEqual(manifest.get("benchmark"), {"p95_latency_ms": 14.5, "fault_false_safe_count": 0})
            self.assertEqual(manifest.get("classes"), ["breadboard", "resistor", "wire", "led"])
            self.assertEqual(
                set(manifest.get("capabilities", [])),
                {"component_detection", "wire_instance_segmentation", "terminal_localization"},
            )

    def test_write_engine_manifest_exceeds_latency_gate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            engine_path = root / "detector.engine"
            engine_path.write_bytes(b"engine_bytes")

            result = run_cli_tool(
                "write_engine_manifest.py",
                [
                    str(engine_path),
                    "--target-gpu", "RTX 3060",
                    "--p95-latency-ms", "180.0",  # Limit is 150ms
                    "--fault-false-safe-count", "0",
                    "--classes", "resistor",
                    "--capabilities", "component_detection", "wire_instance_segmentation", "terminal_localization",
                ],
            )
            self.assertNotEqual(result.returncode, 0)
            output = result.stderr + result.stdout
            self.assertIn("Engine benchmark does not meet CircuitPulse safety/latency gates", output)

    def test_write_engine_manifest_nonzero_false_safes_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            engine_path = root / "detector.engine"
            engine_path.write_bytes(b"engine_bytes")

            result = run_cli_tool(
                "write_engine_manifest.py",
                [
                    str(engine_path),
                    "--target-gpu", "RTX 4090",
                    "--p95-latency-ms", "10.0",
                    "--fault-false-safe-count", "1",  # Must be 0
                    "--classes", "resistor",
                    "--capabilities", "component_detection", "wire_instance_segmentation", "terminal_localization",
                ],
            )
            self.assertNotEqual(result.returncode, 0)
            output = result.stderr + result.stdout
            self.assertIn("Engine benchmark does not meet CircuitPulse safety/latency gates", output)

    def test_write_engine_manifest_missing_required_capability(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            engine_path = root / "detector.engine"
            engine_path.write_bytes(b"engine_bytes")

            result = run_cli_tool(
                "write_engine_manifest.py",
                [
                    str(engine_path),
                    "--target-gpu", "RTX 4090",
                    "--p95-latency-ms", "10.0",
                    "--fault-false-safe-count", "0",
                    "--classes", "resistor",
                    "--capabilities", "component_detection",  # Missing wire_instance_segmentation and terminal_localization
                ],
            )
            self.assertNotEqual(result.returncode, 0)
            output = result.stderr + result.stdout
            self.assertIn("Engine manifest does not prove the component, wire-segmentation, and terminal-localization capabilities", output)

    def test_write_engine_manifest_missing_engine_file(self):
        result = run_cli_tool(
            "write_engine_manifest.py",
            [
                "nonexistent.engine",
                "--target-gpu", "RTX 4090",
                "--p95-latency-ms", "10.0",
                "--fault-false-safe-count", "0",
                "--classes", "resistor",
                "--capabilities", "component_detection", "wire_instance_segmentation", "terminal_localization",
            ],
        )
        self.assertNotEqual(result.returncode, 0)
        output = result.stderr + result.stdout
        self.assertIn("Engine does not exist", output)


if __name__ == "__main__":
    unittest.main()
