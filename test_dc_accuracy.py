import unittest

from logic.circuit_ir import CircuitIR
from logic.dc_solver import LinearDCSolver


class TestDCAccuracy(unittest.TestCase):
    def setUp(self):
        self.solver = LinearDCSolver()

    def solve(self, components):
        payload = {
            "schema_version": 1,
            "components": components,
            "wires": [],
            "requirements": []
        }
        circuit = CircuitIR(payload)
        return self.solver.solve(circuit, "gnd")

    def test_ohms_law(self):
        res = self.solve([
            {"id": "V1", "type": "voltage_source", "voltage_v": 5.0, "pins": {"+": "vcc", "-": "gnd"}},
            {"id": "R1", "type": "resistor", "value_ohms": 1000, "pins": {"1": "vcc", "2": "gnd"}}
        ])
        self.assertEqual(res["status"], "PASS")
        self.assertAlmostEqual(res["branch_currents"]["R1"]["i_a"], 0.005, places=5)

    def test_voltage_divider(self):
        res = self.solve([
            {"id": "V1", "type": "voltage_source", "voltage_v": 5.0, "pins": {"+": "vcc", "-": "gnd"}},
            {"id": "R1", "type": "resistor", "value_ohms": 10000, "pins": {"1": "vcc", "2": "mid"}},
            {"id": "R2", "type": "resistor", "value_ohms": 10000, "pins": {"1": "mid", "2": "gnd"}}
        ])
        self.assertAlmostEqual(res["node_voltages_v"]["mid"], 2.5, places=5)

    def test_unequal_divider(self):
        res = self.solve([
            {"id": "V1", "type": "voltage_source", "voltage_v": 5.0, "pins": {"+": "vcc", "-": "gnd"}},
            {"id": "R1", "type": "resistor", "value_ohms": 10000, "pins": {"1": "vcc", "2": "mid"}},
            {"id": "R2", "type": "resistor", "value_ohms": 20000, "pins": {"1": "mid", "2": "gnd"}}
        ])
        self.assertAlmostEqual(res["node_voltages_v"]["mid"], 3.333333, places=3)

    def test_three_resistors_in_series(self):
        res = self.solve([
            {"id": "V1", "type": "voltage_source", "voltage_v": 5.0, "pins": {"+": "vcc", "-": "gnd"}},
            {"id": "R1", "type": "resistor", "value_ohms": 1000, "pins": {"1": "vcc", "2": "n1"}},
            {"id": "R2", "type": "resistor", "value_ohms": 2000, "pins": {"1": "n1", "2": "n2"}},
            {"id": "R3", "type": "resistor", "value_ohms": 2000, "pins": {"1": "n2", "2": "gnd"}}
        ])
        self.assertAlmostEqual(res["node_voltages_v"]["n1"], 4.0, places=5)
        self.assertAlmostEqual(res["node_voltages_v"]["n2"], 2.0, places=5)

    def test_led_forward_voltage(self):
        res = self.solve([
            {"id": "V1", "type": "voltage_source", "voltage_v": 5.0, "pins": {"+": "vcc", "-": "gnd"}},
            {"id": "R1", "type": "resistor", "value_ohms": 220, "pins": {"1": "vcc", "2": "led_a"}},
            {"id": "D1", "type": "led", "forward_voltage_v": 2.0, "pins": {"anode": "led_a", "cathode": "gnd"}}
        ])
        # total series resistance for diode model is 10.0
        # total resistance = 220 + 10 = 230
        # V = 5 - 2 = 3
        # I = 3 / 230 = 0.013043
        self.assertAlmostEqual(res["branch_currents"]["R1"]["i_a"], 0.013043, places=4)

    def test_red_led(self):
        res = self.solve([
            {"id": "V1", "type": "voltage_source", "voltage_v": 5.0, "pins": {"+": "vcc", "-": "gnd"}},
            {"id": "R1", "type": "resistor", "value_ohms": 330, "pins": {"1": "vcc", "2": "led_a"}},
            {"id": "D1", "type": "led", "forward_voltage_v": 1.8, "pins": {"anode": "led_a", "cathode": "gnd"}}
        ])
        # I = (5.0 - 1.8) / (330 + 10) = 3.2 / 340 = 0.00941
        self.assertAlmostEqual(res["branch_currents"]["R1"]["i_a"], 0.00941, places=4)

    def test_two_leds_in_series(self):
        res = self.solve([
            {"id": "V1", "type": "voltage_source", "voltage_v": 5.0, "pins": {"+": "vcc", "-": "gnd"}},
            {"id": "R1", "type": "resistor", "value_ohms": 100, "pins": {"1": "vcc", "2": "n1"}},
            {"id": "D1", "type": "led", "forward_voltage_v": 1.5, "pins": {"anode": "n1", "cathode": "n2"}},
            {"id": "D2", "type": "led", "forward_voltage_v": 1.5, "pins": {"anode": "n2", "cathode": "gnd"}}
        ])
        # I = (5 - 3) / (100 + 10 + 10) = 2 / 120 = 0.016666
        self.assertAlmostEqual(res["branch_currents"]["R1"]["i_a"], 0.01666, places=4)

    def test_diode_forward_drop(self):
        res = self.solve([
            {"id": "V1", "type": "voltage_source", "voltage_v": 5.0, "pins": {"+": "vcc", "-": "gnd"}},
            {"id": "R1", "type": "resistor", "value_ohms": 1000, "pins": {"1": "vcc", "2": "n1"}},
            {"id": "D1", "type": "diode", "forward_voltage_v": 0.7, "pins": {"anode": "n1", "cathode": "gnd"}}
        ])
        # I = (5.0 - 0.7) / (1000 + 10) = 4.3 / 1010 = 0.004257
        self.assertAlmostEqual(res["branch_currents"]["R1"]["i_a"], 0.004257, places=4)

    def test_current_source(self):
        res = self.solve([
            {"id": "I1", "type": "current_source", "current_ma": 10.0, "pins": {"+": "gnd", "-": "n1"}},
            {"id": "R1", "type": "resistor", "value_ohms": 1000, "pins": {"1": "n1", "2": "gnd"}}
        ])
        # current pushes into n1
        self.assertAlmostEqual(res["node_voltages_v"]["n1"], 10.0, places=4)

    def test_multiple_voltage_sources(self):
        res = self.solve([
            {"id": "V1", "type": "voltage_source", "voltage_v": 5.0, "pins": {"+": "v5", "-": "gnd"}},
            {"id": "V2", "type": "voltage_source", "voltage_v": 3.3, "pins": {"+": "v33", "-": "gnd"}},
            {"id": "R1", "type": "resistor", "value_ohms": 1000, "pins": {"1": "v5", "2": "mid"}},
            {"id": "R2", "type": "resistor", "value_ohms": 1000, "pins": {"1": "v33", "2": "mid"}}
        ])
        self.assertAlmostEqual(res["node_voltages_v"]["mid"], 4.15, places=4)

    def test_branch_current_accuracy(self):
        res = self.solve([
            {"id": "V1", "type": "voltage_source", "voltage_v": 5.0, "pins": {"+": "vcc", "-": "gnd"}},
            {"id": "R1", "type": "resistor", "value_ohms": 1000, "pins": {"1": "vcc", "2": "gnd"}}
        ])
        self.assertEqual(res["branch_currents"]["R1"]["i_a"], 0.005)

    def test_power_dissipation_accuracy(self):
        res = self.solve([
            {"id": "V1", "type": "voltage_source", "voltage_v": 5.0, "pins": {"+": "vcc", "-": "gnd"}},
            {"id": "R1", "type": "resistor", "value_ohms": 1000, "pins": {"1": "vcc", "2": "gnd"}}
        ])
        self.assertAlmostEqual(res["branch_currents"]["R1"]["p_w"], 0.025, places=5)

    def test_capacitor_as_open_circuit(self):
        res = self.solve([
            {"id": "V1", "type": "voltage_source", "voltage_v": 5.0, "pins": {"+": "vcc", "-": "gnd"}},
            {"id": "R1", "type": "resistor", "value_ohms": 1000, "pins": {"1": "vcc", "2": "mid"}},
            {"id": "R2", "type": "resistor", "value_ohms": 1000, "pins": {"1": "mid", "2": "gnd"}},
            {"id": "C1", "type": "capacitor", "pins": {"1": "mid", "2": "gnd"}}
        ])
        self.assertAlmostEqual(res["node_voltages_v"]["mid"], 2.5, places=4)

    def test_inductor_as_short_circuit(self):
        res = self.solve([
            {"id": "V1", "type": "voltage_source", "voltage_v": 5.0, "pins": {"+": "vcc", "-": "gnd"}},
            {"id": "R1", "type": "resistor", "value_ohms": 1000, "pins": {"1": "vcc", "2": "mid"}},
            {"id": "L1", "type": "inductor", "pins": {"1": "mid", "2": "gnd"}}
        ])
        # R1 is 1000, L1 is 0.001
        expected_v = 5.0 * 0.001 / 1000.001
        self.assertAlmostEqual(res["node_voltages_v"]["mid"], expected_v, places=4)

    def test_custom_led_vf(self):
        res = self.solve([
            {"id": "V1", "type": "voltage_source", "voltage_v": 5.0, "pins": {"+": "vcc", "-": "gnd"}},
            {"id": "R1", "type": "resistor", "value_ohms": 100, "pins": {"1": "vcc", "2": "led_a"}},
            {"id": "D1", "type": "led", "forward_voltage_v": 3.2, "pins": {"anode": "led_a", "cathode": "gnd"}}
        ])
        # I = (5.0 - 3.2) / (100 + 10) = 1.8 / 110 = 0.016363
        self.assertAlmostEqual(res["branch_currents"]["R1"]["i_a"], 0.01636, places=4)

    def test_dense_pathological_graph(self):
        # Create a fully connected graph of 10 nodes (45 resistors)
        components = [{"id": "V1", "type": "voltage_source", "voltage_v": 5.0, "pins": {"+": "n0", "-": "gnd"}}]
        for i in range(10):
            for j in range(i + 1, 10):
                n1 = f"n{i}" if i > 0 else "gnd"
                n2 = f"n{j}"
                components.append({"id": f"R_{i}_{j}", "type": "resistor", "value_ohms": 1.0, "pins": {"1": n1, "2": n2}})
        res = self.solve(components)
        self.assertEqual(res["status"], "PASS")
        # With V=5V connected between n0 and gnd, and 1-ohm resistors between all pairs
        # The node voltages should be symmetric and solvable without numerical crash
        self.assertIn("n1", res["node_voltages_v"])

if __name__ == '__main__':
    unittest.main()
