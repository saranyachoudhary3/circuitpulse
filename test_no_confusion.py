import unittest
from logic.logic_engine import CircuitLogicEngine

class TestNoConfusion(unittest.TestCase):
    def setUp(self):
        self.engine = CircuitLogicEngine()

    def run_scenario(self, components, requirements=None):
        if requirements is None:
            requirements = []
        if not any(c.get("type") == "supply" for c in components):
            components.append({"id": "sys_pwr", "type": "supply", "pins": {"positive": "5V", "negative": "GND"}})
        payload = {"components": components, "requirements": requirements}
        return self.engine.analyze(payload)

    def test_01_led_with_resistor(self):
        res = self.run_scenario([
            {"id": "led", "type": "led", "pins": {"anode": "5V", "cathode": "CATH"}},
            {"id": "r1", "type": "resistor", "value_ohms": 330, "pins": {"1": "CATH", "2": "GND"}},
            {"id": "arduino", "type": "arduino", "pins": {"5V": "5V", "GND": "GND"}}
        ])
        self.assertEqual(res["status"], "PASS")

    def test_01_led_without_resistor(self):
        res = self.run_scenario([
            {"id": "led", "type": "led", "pins": {"anode": "5V", "cathode": "GND"}},
            {"id": "arduino", "type": "arduino", "pins": {"5V": "5V", "GND": "GND"}}
        ])
        self.assertEqual(res["status"], "FAIL")
        self.assertTrue(any(w["code"] == "LED_CURRENT_LIMITER_MISSING" for w in res["findings"]))

    def test_02_motor_flyback(self):
        res = self.run_scenario([
            {"id": "m", "type": "dc_motor", "pins": {"1": "5V", "2": "C"}},
            {"id": "d", "type": "diode", "pins": {"anode": "C", "cathode": "5V"}},
            {"id": "t", "type": "2n2222_bjt", "pins": {"collector": "C", "emitter": "GND", "base": "B"}},
            {"id": "r", "type": "resistor", "value_ohms": 1000, "pins": {"1": "D2", "2": "B"}},
        ], requirements=[{"kind": "inductive_load", "component_id": "m"}])
        self.assertEqual(res["status"], "PASS")

    def test_02_motor_flyback_reversed(self):
        res = self.run_scenario([
            {"id": "m", "type": "dc_motor", "pins": {"1": "5V", "2": "C"}},
            {"id": "d", "type": "diode", "pins": {"anode": "5V", "cathode": "C"}},
            {"id": "t", "type": "2n2222_bjt", "pins": {"collector": "C", "emitter": "GND", "base": "B"}},
            {"id": "r", "type": "resistor", "value_ohms": 1000, "pins": {"1": "D2", "2": "B"}},
        ], requirements=[{"kind": "inductive_load", "component_id": "m"}])
        self.assertEqual(res["status"], "FAIL")
        self.assertTrue(any(w["code"] == "FLYBACK_DIODE_REVERSED" or w["code"] == "DIRECT_POWER_SHORT" or w["code"] == "COMPONENT_VOLTAGE_RATING_EXCEEDED" or w["code"] == "INDUCTIVE_LOAD_NO_FLYBACK" for w in res["findings"]))

    def test_03_button_pullup(self):
        res = self.run_scenario([
            {"id": "b1", "type": "button", "pins": {"1": "D2", "2": "GND"}},
            {"id": "rp1", "type": "resistor", "value_ohms": 10000, "pins": {"1": "5V", "2": "D2"}},
        ])
        self.assertEqual(res["status"], "PASS")

    def test_03_button_no_pullup(self):
        res = self.run_scenario([
            {"id": "b1", "type": "button", "pins": {"1": "D2", "2": "GND"}},
            {"id": "arduino", "type": "arduino", "pins": {"5V": "5V", "GND": "GND", "D2": "D2"}}
        ])
        self.assertEqual(res["status"], "INDETERMINATE")
        self.assertTrue(any(w["code"] == "FLOATING_INPUT" for w in res["findings"]))

    def test_04_correct_voltage_divider(self):
        res = self.run_scenario([
            {"id": "r1", "type": "resistor", "value_ohms": 10000, "pins": {"1": "5V", "2": "A0"}},
            {"id": "r2", "type": "resistor", "value_ohms": 10000, "pins": {"1": "A0", "2": "GND"}},
            {"id": "arduino", "type": "arduino", "pins": {"5V": "5V", "GND": "GND", "A0": "A0"}}
        ], requirements=[{"kind": "voltage_divider", "output_net": "A0", "upper_resistor": "r1", "lower_resistor": "r2", "input_voltage_v": 5.0, "output_min_v": 0.0, "output_max_v": 3.0}])
        self.assertEqual(res["status"], "PASS")

    def test_04_wrong_ratio_divider(self):
        res = self.run_scenario([
            {"id": "r1", "type": "resistor", "value_ohms": 1000, "pins": {"1": "5V", "2": "A0"}},
            {"id": "r2", "type": "resistor", "value_ohms": 100000, "pins": {"1": "A0", "2": "GND"}},
            {"id": "arduino", "type": "arduino", "pins": {"5V": "5V", "GND": "GND", "A0": "A0"}}
        ], requirements=[{"kind": "voltage_divider", "output_net": "A0", "upper_resistor": "r1", "lower_resistor": "r2", "input_voltage_v": 5.0, "output_min_v": 0.0, "output_max_v": 3.0}])
        self.assertEqual(res["status"], "FAIL")

    def test_05_i2c_with_pullups(self):
        res = self.run_scenario([
            {"id": "dev", "type": "i2c_sensor", "i2c_address": "0x40", "pins": {"VCC": "5V", "GND": "GND", "SDA": "SDA", "SCL": "SCL"}},
            {"id": "rp1", "type": "resistor", "value_ohms": 4700, "pins": {"1": "5V", "2": "SDA"}},
            {"id": "rp2", "type": "resistor", "value_ohms": 4700, "pins": {"1": "5V", "2": "SCL"}},
            {"id": "arduino", "type": "arduino", "pins": {"5V": "5V", "GND": "GND", "SDA": "SDA", "SCL": "SCL"}}
        ], requirements=[{"kind": "i2c", "sda_net": "SDA", "scl_net": "SCL", "supply_net": "5V", "pullup_resistors": ["rp1", "rp2"]}])
        self.assertEqual(res["status"], "PASS")

    def test_05_i2c_without_pullups(self):
        res = self.run_scenario([
            {"id": "dev", "type": "i2c_sensor", "i2c_address": "0x40", "pins": {"VCC": "5V", "GND": "GND", "SDA": "SDA", "SCL": "SCL"}},
            {"id": "arduino", "type": "arduino", "pins": {"5V": "5V", "GND": "GND", "SDA": "SDA", "SCL": "SCL"}}
        ], requirements=[{"kind": "i2c", "sda_net": "SDA", "scl_net": "SCL", "supply_net": "5V", "pullup_resistors": []}])
        self.assertEqual(res["status"], "FAIL")

    def test_06_cap_polarity(self):
        res = self.run_scenario([
            {"id": "c", "type": "electrolytic_capacitor", "value_farads": 0.0001, "pins": {"positive": "5V", "negative": "GND"}},
            {"id": "arduino", "type": "arduino", "pins": {"5V": "5V", "GND": "GND"}}
        ])
        self.assertEqual(res["status"], "PASS")

    def test_06_cap_reversed(self):
        res = self.run_scenario([
            {"id": "c", "type": "electrolytic_capacitor", "value_farads": 0.0001, "pins": {"positive": "GND", "negative": "5V"}},
            {"id": "arduino", "type": "arduino", "pins": {"5V": "5V", "GND": "GND"}}
        ])
        self.assertEqual(res["status"], "FAIL")
        self.assertTrue(any(w["code"] == "CAPACITOR_REVERSED_POLARITY" for w in res["findings"]))

    def test_07_open_drain(self):
        res = self.run_scenario([
            {"id": "sensor", "type": "i2c_sensor", "i2c_address": "0x40", "pins": {"VCC": "5V", "GND": "GND", "SDA": "SDA", "SCL": "SCL"}},
            {"id": "rp1", "type": "resistor", "value_ohms": 4700, "pins": {"1": "5V", "2": "SDA"}},
            {"id": "rp2", "type": "resistor", "value_ohms": 4700, "pins": {"1": "5V", "2": "SCL"}},
            {"id": "arduino", "type": "arduino", "pins": {"5V": "5V", "GND": "GND", "SDA": "SDA", "SCL": "SCL"}}
        ])
        self.assertEqual(res["status"], "PASS")

    def test_07_push_pull(self):
        res = self.run_scenario([
            {"id": "led", "type": "led", "pins": {"anode": "5V", "cathode": "CATH"}},
            {"id": "r1", "type": "resistor", "value_ohms": 330, "pins": {"1": "CATH", "2": "GND"}},
            {"id": "arduino", "type": "arduino", "pins": {"5V": "5V", "GND": "GND"}}
        ])
        self.assertEqual(res["status"], "PASS")

    def test_08_power_budget_under(self):
        res = self.run_scenario([
            {"id": "led", "type": "led", "pins": {"anode": "5V", "cathode": "CATH"}},
            {"id": "r1", "type": "resistor", "value_ohms": 330, "pins": {"1": "CATH", "2": "GND"}},
            {"id": "arduino", "type": "arduino", "pins": {"5V": "5V", "GND": "GND"}}
        ], requirements=[{"kind": "current_budget", "source_id": "arduino", "available_current_ma": 500, "loads": [{"component_id": "led", "current_ma": 20}]}])
        self.assertEqual(res["status"], "PASS")

    def test_08_power_budget_over(self):
        res = self.run_scenario([
            {"id": "m1", "type": "dc_motor", "pins": {"1": "5V", "2": "GND"}},
            {"id": "m2", "type": "dc_motor", "pins": {"1": "5V", "2": "GND"}},
            {"id": "arduino", "type": "arduino", "pins": {"5V": "5V", "GND": "GND"}}
        ], requirements=[{"kind": "current_budget", "source_id": "arduino", "available_current_ma": 500, "loads": [{"component_id": "m1", "current_ma": 400}, {"component_id": "m2", "current_ma": 400}]}])
        self.assertEqual(res["status"], "FAIL")
        self.assertTrue(any(w["code"] == "CURRENT_BUDGET_EXCEEDED" for w in res["findings"]))

    def test_09_divider_in_range(self):
        res = self.run_scenario([
            {"id": "r1", "type": "resistor", "value_ohms": 10000, "pins": {"1": "5V", "2": "A0"}},
            {"id": "r2", "type": "resistor", "value_ohms": 10000, "pins": {"1": "A0", "2": "GND"}},
            {"id": "r3_load", "type": "resistor", "value_ohms": 1000000, "pins": {"1": "A0", "2": "GND"}},
            {"id": "arduino", "type": "arduino", "pins": {"5V": "5V", "GND": "GND", "A0": "A0"}}
        ], requirements=[{"kind": "voltage_divider", "output_net": "A0", "upper_resistor": "r1", "lower_resistor": "r2", "input_voltage_v": 5.0, "output_min_v": 2.0, "output_max_v": 3.0, "load_resistance_ohms": 1000000}])
        self.assertEqual(res["status"], "PASS")

    def test_09_divider_sag(self):
        res = self.run_scenario([
            {"id": "r1", "type": "resistor", "value_ohms": 10000, "pins": {"1": "5V", "2": "A0"}},
            {"id": "r2", "type": "resistor", "value_ohms": 10000, "pins": {"1": "A0", "2": "GND"}},
            {"id": "r3_load", "type": "resistor", "value_ohms": 100, "pins": {"1": "A0", "2": "GND"}},
            {"id": "arduino", "type": "arduino", "pins": {"5V": "5V", "GND": "GND", "A0": "A0"}}
        ], requirements=[{"kind": "voltage_divider", "output_net": "A0", "upper_resistor": "r1", "lower_resistor": "r2", "input_voltage_v": 5.0, "output_min_v": 2.0, "output_max_v": 3.0, "load_resistance_ohms": 100}])
        self.assertEqual(res["status"], "FAIL")
        self.assertTrue(any(w["code"] == "VOLTAGE_DIVIDER_LOADED_SAG" or w["code"] == "DIVIDER_OUTPUT_OUT_OF_RANGE" for w in res["findings"]))

    def test_10_resistor_on_gpio(self):
        res = self.run_scenario([
            {"id": "r1", "type": "resistor", "value_ohms": 1000, "pins": {"1": "D2", "2": "GND"}},
            {"id": "arduino", "type": "arduino", "pins": {"5V": "5V", "D2": "D2", "GND": "GND"}}
        ])
        self.assertEqual(res["status"], "PASS")

    def test_10_self_short(self):
        res = self.run_scenario([
            {"id": "r1", "type": "resistor", "value_ohms": 1000, "pins": {"1": "D2", "2": "D2"}},
            {"id": "arduino", "type": "arduino", "pins": {"5V": "5V", "D2": "D2", "GND": "GND"}}
        ])
        self.assertEqual(res["status"], "FAIL")
        self.assertTrue(any(w["code"] == "COMPONENT_SELF_SHORT" for w in res["findings"]))

    def test_11_multiple_faults(self):
        res = self.run_scenario([
            {"id": "r1", "type": "resistor", "value_ohms": 1000, "pins": {"1": "D2", "2": "D2"}},
            {"id": "led", "type": "led", "pins": {"anode": "5V", "cathode": "GND"}},
            {"id": "arduino", "type": "arduino", "pins": {"5V": "5V", "D2": "D2", "GND": "GND"}}
        ])
        self.assertEqual(res["status"], "FAIL")

    def test_12_power_short_i2c(self):
        res = self.run_scenario([
            {"id": "r1", "type": "resistor", "value_ohms": 1000, "pins": {"1": "5V", "2": "5V"}},
            {"id": "arduino", "type": "arduino", "pins": {"5V": "5V", "GND": "GND"}}
        ])
        self.assertEqual(res["status"], "FAIL")

    def test_13_firmware(self):
        res = self.run_scenario([
            {"id": "arduino", "type": "arduino", "pins": {"5V": "5V", "GND": "GND"}}
        ], requirements=[{"kind": "firmware", "code": ""}])
        self.assertEqual(res["status"], "INDETERMINATE")

    def test_14_empty(self):
        payload = {"components": [], "requirements": []}
        with self.assertRaises(Exception):
            self.engine.analyze(payload)

    def test_15_inductive_load_unconnected(self):
        res = self.run_scenario([
            {"id": "m1", "type": "dc_motor", "pins": {"1": "NC", "2": "NC2"}},
            {"id": "arduino", "type": "arduino", "pins": {"5V": "5V", "GND": "GND"}}
        ])
        self.assertEqual(res["status"], "PASS")

    def test_16_led_on_wrong_pin(self):
        res_pass = self.run_scenario([
            {"id": "led", "type": "led", "pins": {"anode": "5V", "cathode": "MID"}},
            {"id": "r1", "type": "resistor", "value_ohms": 330, "pins": {"1": "MID", "2": "GND"}},
            {"id": "arduino", "type": "arduino", "pins": {"5V": "5V", "GND": "GND", "D2": "D2"}}
        ])
        res_fail = self.run_scenario([
            {"id": "led", "type": "led", "pins": {"anode": "NC", "cathode": "MID"}},
            {"id": "r1", "type": "resistor", "value_ohms": 330, "pins": {"1": "MID", "2": "GND"}},
            {"id": "arduino", "type": "arduino", "pins": {"5V": "5V", "GND": "GND"}}
        ])
        self.assertEqual(res_pass["status"], "PASS")
        self.assertEqual(res_fail["status"], "FAIL") 

    def test_17_relay_direct_gpio(self):
        res_pass = self.run_scenario([
            {"id": "m", "type": "dc_motor", "pins": {"1": "5V", "2": "C"}},
            {"id": "d", "type": "diode", "pins": {"anode": "C", "cathode": "5V"}},
            {"id": "t", "type": "2n2222_bjt", "pins": {"collector": "C", "emitter": "GND", "base": "B"}},
            {"id": "r", "type": "resistor", "value_ohms": 1000, "pins": {"1": "D2", "2": "B"}}
        ], requirements=[{"kind": "inductive_load", "component_id": "m"}])
        
        res_fail = self.run_scenario([
            {"id": "m", "type": "dc_motor", "pins": {"1": "D2", "2": "GND"}},
            {"id": "arduino", "type": "arduino", "pins": {"5V": "5V", "GND": "GND", "D2": "D2"}}
        ], requirements=[{"kind": "inductive_load", "component_id": "m"}])
        
        self.assertEqual(res_pass["status"], "PASS")
        self.assertEqual(res_fail["status"], "FAIL")
        self.assertTrue(any("MOTOR_DIRECT_GPIO" in w["code"] or "INDUCTIVE_LOAD" in w["code"] or "CURRENT_BUDGET" in w["code"] or "NO_FLYBACK" in w["code"] for w in res_fail["findings"]))

    def test_18_potentiometer(self):
        res_pass = self.run_scenario([
            {"id": "pot", "type": "potentiometer", "value_ohms": 10000, "pins": {"1": "5V", "2": "GND", "wiper": "A0"}},
            {"id": "arduino", "type": "arduino", "pins": {"5V": "5V", "GND": "GND", "A0": "A0"}}
        ])
        res_fail = self.run_scenario([
            {"id": "pot", "type": "potentiometer", "value_ohms": 10000, "pins": {"1": "5V", "2": "GND", "wiper": "NC"}},
            {"id": "arduino", "type": "arduino", "pins": {"5V": "5V", "GND": "GND", "A0": "A0"}}
        ])
        self.assertEqual(res_pass["status"], "PASS")

    def test_19_resistors_series_parallel(self):
        res_series = self.run_scenario([
            {"id": "r1", "type": "resistor", "value_ohms": 100, "pins": {"1": "5V", "2": "MID"}},
            {"id": "r2", "type": "resistor", "value_ohms": 200, "pins": {"1": "MID", "2": "GND"}},
            {"id": "arduino", "type": "arduino", "pins": {"5V": "5V", "GND": "GND"}}
        ])
        res_parallel = self.run_scenario([
            {"id": "r1", "type": "resistor", "value_ohms": 100, "pins": {"1": "5V", "2": "GND"}},
            {"id": "r2", "type": "resistor", "value_ohms": 100, "pins": {"1": "5V", "2": "GND"}},
            {"id": "arduino", "type": "arduino", "pins": {"5V": "5V", "GND": "GND"}}
        ])
        self.assertEqual(res_series["status"], "PASS")
        self.assertEqual(res_parallel["status"], "PASS")

    def test_20_three_independent_faults(self):
        res_fail = self.run_scenario([
            {"id": "r_short", "type": "resistor", "value_ohms": 1000, "pins": {"1": "D2", "2": "D2"}}, # 1. self short
            {"id": "led", "type": "led", "pins": {"anode": "5V", "cathode": "GND"}}, # 2. led missing resistor
            {"id": "c_rev", "type": "electrolytic_capacitor", "value_farads": 0.0001, "pins": {"positive": "GND", "negative": "5V"}}, # 3. reversed capacitor
            {"id": "arduino", "type": "arduino", "pins": {"5V": "5V", "GND": "GND", "D2": "D2"}}
        ])
        self.assertEqual(res_fail["status"], "FAIL")
        codes = [w["code"] for w in res_fail["findings"]]
        self.assertTrue(any("SELF_SHORT" in c for c in codes))
        self.assertTrue(any("LED_CURRENT_LIMITER_MISSING" in c for c in codes))
        self.assertTrue(any("CAPACITOR_REVERSED_POLARITY" in c for c in codes))
