import unittest
from logic.dc_solver import LinearDCSolver
from logic.circuit_ir import CircuitIR

class TestDCSolverV2(unittest.TestCase):
    def setUp(self):
        self.solver = LinearDCSolver()
        
    def make_cir(self, *components):
        return CircuitIR({"schema_version": 1, "components": [{"id": f"c{i+1}", **c} for i, c in enumerate(components)]})

    def test_resistor_divider(self):
        cir = self.make_cir({"type": "voltage_source", "voltage_v": 10.0, "pins": {"positive": "vcc", "negative": "gnd"}}, {"type": "resistor", "value_ohms": 1000, "pins": {"1": "vcc", "2": "mid"}}, {"type": "resistor", "value_ohms": 1000, "pins": {"1": "mid", "2": "gnd"}})
        res = self.solver.solve(cir, "gnd")
        self.assertEqual(res["status"], "PASS")
        self.assertAlmostEqual(res["node_voltages_v"]["mid"], 5.0)

    def test_led_resistor(self):
        cir = self.make_cir({"type": "voltage_source", "voltage_v": 5.0, "pins": {"+": "vcc", "-": "gnd"}}, {"type": "led", "pins": {"anode": "vcc", "cathode": "mid"}}, {"type": "resistor", "value_ohms": 220, "pins": {"1": "mid", "2": "gnd"}})
        res = self.solver.solve(cir, "gnd")
        self.assertEqual(res["status"], "PASS")
        i_ma = res["branch_currents"]["c3"]["i_a"] * 1000
        self.assertAlmostEqual(i_ma, 13.04, places=1)

    def test_capacitor_open(self):
        cir = self.make_cir({"type": "voltage_source", "voltage_v": 5.0, "pins": {"+": "vcc", "-": "gnd"}}, {"type": "capacitor", "value_f": 1e-6, "pins": {"1": "vcc", "2": "gnd"}}, {"type": "resistor", "value_ohms": 1000, "pins": {"1": "vcc", "2": "gnd"}})
        res = self.solver.solve(cir, "gnd")
        self.assertEqual(res["status"], "PASS")
        self.assertAlmostEqual(res["node_voltages_v"]["vcc"], 5.0)

    def test_inductor_short(self):
        cir = self.make_cir({"type": "voltage_source", "voltage_v": 5.0, "pins": {"+": "vcc", "-": "gnd"}}, {"type": "inductor", "value_h": 1e-6, "pins": {"1": "vcc", "2": "mid"}}, {"type": "resistor", "value_ohms": 1000, "pins": {"1": "mid", "2": "gnd"}})
        res = self.solver.solve(cir, "gnd")
        self.assertEqual(res["status"], "PASS")
        self.assertAlmostEqual(res["node_voltages_v"]["mid"], 5.0, places=2)

    def test_diode_resistor(self):
        cir = self.make_cir({"type": "voltage_source", "voltage_v": 5.0, "pins": {"+": "vcc", "-": "gnd"}}, {"type": "diode", "pins": {"anode": "vcc", "cathode": "mid"}}, {"type": "resistor", "value_ohms": 1000, "pins": {"1": "mid", "2": "gnd"}})
        res = self.solver.solve(cir, "gnd")
        self.assertEqual(res["status"], "PASS")
        v_mid = res["node_voltages_v"]["mid"]
        self.assertAlmostEqual(v_mid, 4.257, places=2)

    def test_custom_forward_voltage(self):
        cir = self.make_cir({"type": "voltage_source", "voltage_v": 5.0, "pins": {"+": "vcc", "-": "gnd"}}, {"type": "led", "forward_voltage_v": 3.0, "pins": {"anode": "vcc", "cathode": "mid"}}, {"type": "resistor", "value_ohms": 200, "pins": {"1": "mid", "2": "gnd"}})
        res = self.solver.solve(cir, "gnd")
        self.assertEqual(res["status"], "PASS")
        i = res["branch_currents"]["c3"]["i_a"]
        self.assertAlmostEqual(i, 0.00952, places=3)

    def test_branch_currents_returned(self):
        cir = self.make_cir({"type": "voltage_source", "voltage_v": 10.0, "pins": {"+": "vcc", "-": "gnd"}}, {"type": "resistor", "value_ohms": 5, "pins": {"1": "vcc", "2": "gnd"}})
        res = self.solver.solve(cir, "gnd")
        self.assertEqual(res["branch_currents"]["c2"]["i_a"], 2.0)
        self.assertEqual(res["branch_currents"]["c2"]["p_w"], 20.0)

    def test_parallel_voltage_sources(self):
        cir = self.make_cir({"type": "voltage_source", "voltage_v": 5.0, "pins": {"+": "vcc", "-": "gnd"}}, {"type": "voltage_source", "voltage_v": 5.0, "pins": {"+": "vcc", "-": "gnd"}})
        res = self.solver.solve(cir, "gnd")
        self.assertEqual(res["status"], "INDETERMINATE")

    def test_transistor_indeterminate(self):
        cir = self.make_cir({"type": "transistor", "pins": {"b": "a", "c": "b", "e": "c"}})
        res = self.solver.solve(cir, "gnd")
        self.assertEqual(res["status"], "INDETERMINATE")

    def test_floating_node(self):
        cir = self.make_cir({"type": "resistor", "value_ohms": 1000, "pins": {"1": "float1", "2": "float2"}})
        res = self.solver.solve(cir, "gnd")
        self.assertEqual(res["status"], "INDETERMINATE")

    def test_zero_resistance(self):
        cir = self.make_cir({"type": "resistor", "value_ohms": 0, "pins": {"1": "vcc", "2": "gnd"}})
        with self.assertRaises(Exception):
            self.solver.solve(cir, "gnd")

    def test_single_resistor_current(self):
        cir = self.make_cir({"type": "voltage_source", "voltage_v": 10.0, "pins": {"+": "vcc", "-": "gnd"}}, {"type": "resistor", "value_ohms": 100, "pins": {"1": "vcc", "2": "gnd"}})
        res = self.solver.solve(cir, "gnd")
        self.assertEqual(res["branch_currents"]["c2"]["i_a"], 0.1)

    def test_single_resistor_power(self):
        cir = self.make_cir({"type": "voltage_source", "voltage_v": 10.0, "pins": {"+": "vcc", "-": "gnd"}}, {"type": "resistor", "value_ohms": 100, "pins": {"1": "vcc", "2": "gnd"}})
        res = self.solver.solve(cir, "gnd")
        self.assertEqual(res["branch_currents"]["c2"]["p_w"], 1.0)
        
    def test_capacitor_only(self):
        cir = self.make_cir({"type": "capacitor", "value_f": 1e-6, "pins": {"1": "a", "2": "b"}})
        with self.assertRaises(Exception):
            self.solver.solve(cir, "gnd")
        
    def test_inductor_voltage(self):
        cir = self.make_cir({"type": "voltage_source", "voltage_v": 5.0, "pins": {"+": "vcc", "-": "gnd"}}, {"type": "inductor", "value_h": 1e-6, "pins": {"1": "vcc", "2": "gnd"}})
        res = self.solver.solve(cir, "gnd")
        self.assertEqual(res["status"], "PASS")

if __name__ == '__main__':
    unittest.main()
