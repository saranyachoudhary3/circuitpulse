import tempfile
import unittest
from pathlib import Path

from logic.trace_import import TraceImportError, import_logic_csv, import_voltage_csv


class LogicTraceImportTests(unittest.TestCase):
    def test_imports_timestamped_csv_with_explicit_signal_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = Path(directory) / "capture.csv"
            capture.write_text("time_s,CLK,D\n0.000000,0,LOW\n0.000010,HIGH,1\n", encoding="utf-8")
            result = import_logic_csv(capture, {"CLK": "CLK_NET", "D": "D_NET"})
        self.assertEqual(result["sample_count"], 2)
        self.assertEqual(result["measurements"]["digital_trace"][1], {"time_us": 10.0, "levels": {"CLK_NET": 1, "D_NET": 1}})

    def test_rejects_out_of_order_or_unmapped_capture_data(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = Path(directory) / "capture.csv"
            capture.write_text("time_s,CLK\n1,0\n0,1\n", encoding="utf-8")
            with self.assertRaises(TraceImportError):
                import_logic_csv(capture, {"CLK": "CLK_NET"})
            with self.assertRaises(TraceImportError):
                import_logic_csv(capture, {"MISSING": "CLK_NET"})

    def test_imports_voltage_capture_with_explicit_channel_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = Path(directory) / "power.csv"
            capture.write_text("time_s,CH1,CH2\n0,0,0\n0.000010,3.3,1\n", encoding="utf-8")
            result = import_voltage_csv(capture, {"CH1": "VCC", "CH2": "EN"})
        self.assertEqual(result["measurements"]["voltage_trace"][1], {"time_us": 10.0, "voltages_v": {"VCC": 3.3, "EN": 1.0}})
