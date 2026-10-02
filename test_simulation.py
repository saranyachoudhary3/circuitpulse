import subprocess
import unittest
from unittest.mock import patch

from logic.logic_engine import CircuitLogicEngine
from logic.simulation import run_measured_analysis, run_operating_point


NETLIST = """CircuitPulse operating point
V1 vin 0 5
R1 vin vout 1000
R2 vout 0 1000
.op
.print op v(vout)
.end
"""


class SpiceOperatingPointTests(unittest.TestCase):
    def test_missing_simulator_is_indeterminate_not_pass(self):
        with patch("logic.simulation.shutil.which", return_value=None):
            result = run_operating_point(NETLIST, {"vout": [2.0, 3.0]})
        self.assertEqual(result["status"], "INDETERMINATE")

    def test_parser_accepts_reviewed_node_range(self):
        completed = subprocess.CompletedProcess(["ngspice"], 0, "v(vout) = 2.500000e+00\n", "")
        with patch("logic.simulation.shutil.which", return_value="ngspice"), patch("logic.simulation.subprocess.run", return_value=completed):
            result = run_operating_point(NETLIST, {"vout": [2.4, 2.6]})
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["node_voltages_v"]["vout"], 2.5)

    def test_out_of_range_node_is_a_critical_logic_fault(self):
        completed = subprocess.CompletedProcess(["ngspice"], 0, "v(vout) = 2.500000e+00\n", "")
        circuit = {
            "components": [{"id": "V1", "type": "voltage_source", "voltage_v": 5, "pins": {"positive": "VIN", "negative": "GND"}}],
            "requirements": [{"kind": "spice_operating_point", "netlist": NETLIST, "expected_node_ranges_v": {"vout": [0, 2]}}],
        }
        with patch("logic.simulation.shutil.which", return_value="ngspice"), patch("logic.simulation.subprocess.run", return_value=completed):
            result = CircuitLogicEngine().analyze(circuit)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("SPICE_NODE_OUT_OF_RANGE", {item["code"] for item in result["findings"]})

    def test_control_directive_is_rejected_without_subprocess(self):
        with patch("logic.simulation.subprocess.run") as runner:
            result = run_operating_point("V1 a 0 5\n.op\n.control\nshell whoami\n.endc\n.end")
        self.assertEqual(result["status"], "FAIL")
        runner.assert_not_called()

    def test_transient_measurement_range_is_parsed_and_gated(self):
        netlist = "V1 in 0 PULSE(0 5 0 1n 1n 1m 2m)\n.tran 1u 3m\n.meas tran rise_delay when v(in)=2.5 rise=1\n.end\n"
        completed = subprocess.CompletedProcess(["ngspice"], 0, "rise_delay = 2.100000e-03\n", "")
        with patch("logic.simulation.shutil.which", return_value="ngspice"), patch("logic.simulation.subprocess.run", return_value=completed):
            result = run_measured_analysis(netlist, "transient", {"rise_delay": [0.001, 0.002]})
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["out_of_range"][0]["measurement"], "rise_delay")
