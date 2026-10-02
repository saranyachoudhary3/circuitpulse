import unittest
from logic.netlist import NetlistVerifier, PASS, FAIL, INDETERMINATE

class TestNetlistV2(unittest.TestCase):
    def setUp(self):
        self.verifier = NetlistVerifier()

    def test_led_with_cathode_side_resistor(self):
        netlist = {
            "components": [
                {"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}},
                {"id": "D1", "type": "led", "pins": {"anode": "VCC", "cathode": "LED_K"}},
                {"id": "R1", "type": "resistor", "value_ohms": 220, "pins": {"1": "LED_K", "2": "GND"}}
            ]
        }
        res = self.verifier.verify(netlist)
        self.assertEqual(res["status"], PASS)
        self.assertEqual(len(res["findings"]), 0)

    def test_led_with_anode_side_resistor(self):
        netlist = {
            "components": [
                {"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}},
                {"id": "R1", "type": "resistor", "value_ohms": 220, "pins": {"1": "VCC", "2": "LED_A"}},
                {"id": "D1", "type": "led", "pins": {"anode": "LED_A", "cathode": "GND"}}
            ]
        }
        res = self.verifier.verify(netlist)
        self.assertEqual(res["status"], PASS)

    def test_led_with_no_resistor(self):
        netlist = {
            "components": [
                {"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}},
                {"id": "D1", "type": "led", "pins": {"anode": "VCC", "cathode": "GND"}}
            ]
        }
        res = self.verifier.verify(netlist)
        self.assertEqual(res["status"], FAIL)
        self.assertTrue(any(f["code"] == "LED_CURRENT_LIMITER_MISSING" for f in res["findings"]))

    def test_led_reversed(self):
        netlist = {
            "components": [
                {"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}},
                {"id": "R1", "type": "resistor", "value_ohms": 220, "pins": {"1": "VCC", "2": "LED_K"}},
                {"id": "D1", "type": "led", "pins": {"anode": "GND", "cathode": "LED_K"}}
            ]
        }
        res = self.verifier.verify(netlist)
        self.assertEqual(res["status"], FAIL)
        self.assertTrue(any(f["code"] == "LED_REVERSED_POLARITY" for f in res["findings"]))

    def test_resistor_self_short(self):
        netlist = {
            "components": [
                {"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}},
                {"id": "R1", "type": "resistor", "value_ohms": 220, "pins": {"1": "VCC", "2": "VCC"}},
                {"id": "D1", "type": "led", "pins": {"anode": "VCC", "cathode": "GND"}}
            ]
        }
        res = self.verifier.verify(netlist)
        self.assertEqual(res["status"], FAIL)
        self.assertTrue(any(f["code"] == "COMPONENT_SELF_SHORT" for f in res["findings"]))

    def test_normal_resistor_no_self_short(self):
        netlist = {
            "components": [
                {"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}},
                {"id": "R1", "type": "resistor", "value_ohms": 220, "pins": {"1": "VCC", "2": "LED_A"}},
                {"id": "D1", "type": "led", "pins": {"anode": "LED_A", "cathode": "GND"}}
            ]
        }
        res = self.verifier.verify(netlist)
        self.assertFalse(any(f["code"] == "COMPONENT_SELF_SHORT" for f in res["findings"]))

    def test_reversed_electrolytic_capacitor(self):
        netlist = {
            "components": [
                {"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}},
                {"id": "C1", "type": "electrolytic_capacitor", "pins": {"+": "GND", "-": "VCC"}}
            ]
        }
        res = self.verifier.verify(netlist)
        self.assertEqual(res["status"], FAIL)
        self.assertTrue(any(f["code"] == "CAPACITOR_REVERSED_POLARITY" for f in res["findings"]))

    def test_correct_electrolytic_capacitor(self):
        netlist = {
            "components": [
                {"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}},
                {"id": "C1", "type": "electrolytic_capacitor", "pins": {"+": "VCC", "-": "GND"}}
            ]
        }
        res = self.verifier.verify(netlist)
        self.assertEqual(res["status"], PASS)

    def test_motor_on_gpio(self):
        netlist = {
            "components": [
                {"id": "MCU1", "type": "arduino", "pins": {"5V": "VCC", "GND": "GND", "D3": "MOTOR_IN"}},
                {"id": "M1", "type": "motor", "pins": {"1": "MOTOR_IN", "2": "GND"}}
            ]
        }
        res = self.verifier.verify(netlist)
        self.assertEqual(res["status"], FAIL)
        self.assertTrue(any(f["code"] == "MOTOR_DIRECT_GPIO" for f in res["findings"]))

    def test_motor_with_driver(self):
        netlist = {
            "components": [
                {"id": "MCU1", "type": "arduino", "pins": {"5V": "VCC", "GND": "GND", "D3": "DRIVER_IN"}},
                {"id": "IC1", "type": "ic", "pins": {"in": "DRIVER_IN", "out": "MOTOR_IN", "gnd": "GND"}},
                {"id": "M1", "type": "motor", "pins": {"1": "MOTOR_IN", "2": "GND"}}
            ]
        }
        res = self.verifier.verify(netlist)
        self.assertFalse(any(f["code"] == "MOTOR_DIRECT_GPIO" for f in res["findings"]))

    def test_inter_rail_short(self):
        netlist = {
            "components": [
                {"id": "SUPPLY", "type": "supply", "pins": {"5V": "5V_NET", "3V3": "3V3_NET", "GND": "GND"}},
            ],
            "wires": [
                {"from": "5V_NET", "to": "3V3_NET"}
            ]
        }
        res = self.verifier.verify(netlist)
        self.assertEqual(res["status"], FAIL)
        self.assertTrue(any(f["code"] == "INTER_RAIL_SHORT" for f in res["findings"]))

    def test_normal_circuit_separate_rails(self):
        netlist = {
            "components": [
                {"id": "SUPPLY", "type": "supply", "pins": {"5V": "5V_NET", "3V3": "3V3_NET", "GND": "GND"}},
                {"id": "R1", "type": "resistor", "value_ohms": 1000, "pins": {"1": "5V_NET", "2": "GND"}},
                {"id": "R2", "type": "resistor", "value_ohms": 1000, "pins": {"1": "3V3_NET", "2": "GND"}}
            ]
        }
        res = self.verifier.verify(netlist)
        self.assertEqual(res["status"], PASS)

    def test_led_missing_pin_data(self):
        netlist = {
            "components": [
                {"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}},
                {"id": "D1", "type": "led", "pins": {"anode": "VCC"}}
            ]
        }
        res = self.verifier.verify(netlist)
        self.assertEqual(res["status"], FAIL)
        self.assertTrue(any(f["code"] == "LED_PIN_DATA_MISSING" for f in res["findings"]))

    def test_power_short(self):
        netlist = {
            "components": [
                {"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}},
            ],
            "wires": [{"from": "VCC", "to": "GND"}]
        }
        res = self.verifier.verify(netlist)
        self.assertEqual(res["status"], FAIL)
        self.assertTrue(any(f["code"] == "DIRECT_POWER_SHORT" for f in res["findings"]))

    def test_capacitor_non_electrolytic(self):
        netlist = {
            "components": [
                {"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}},
                {"id": "C1", "type": "capacitor", "pins": {"1": "GND", "2": "VCC"}}
            ]
        }
        res = self.verifier.verify(netlist)
        self.assertEqual(res["status"], PASS)

    def test_led_indeterminate_no_power(self):
        netlist = {
            "components": [
                {"id": "D1", "type": "led", "pins": {"anode": "NET1", "cathode": "NET2"}},
                {"id": "R1", "type": "resistor", "value_ohms": 220, "pins": {"1": "NET1", "2": "NET3"}}
            ]
        }
        res = self.verifier.verify(netlist)
        self.assertEqual(res["status"], INDETERMINATE)
        self.assertTrue(any(f["code"] == "MISSING_REFERENCE" for f in res["findings"]))

    def test_motor_safe_power(self):
        netlist = {
            "components": [
                {"id": "MCU", "type": "mcu", "pins": {"5v": "VCC", "GND": "GND", "D1": "SIG"}},
                {"id": "M1", "type": "motor", "pins": {"1": "VCC", "2": "GND"}}
            ]
        }
        res = self.verifier.verify(netlist)
        self.assertEqual(res["status"], PASS)
        self.assertFalse(any(f["code"] == "MOTOR_DIRECT_GPIO" for f in res["findings"]))

    def test_reversed_led_missing_resistor(self):
        netlist = {
            "components": [
                {"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}},
                {"id": "D1", "type": "led", "pins": {"anode": "GND", "cathode": "VCC"}}
            ]
        }
        res = self.verifier.verify(netlist)
        self.assertEqual(res["status"], FAIL)
        codes = {f["code"] for f in res["findings"]}
        self.assertIn("LED_REVERSED_POLARITY", codes)

    def test_resistor_value_unknown(self):
        netlist = {
            "components": [
                {"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}},
                {"id": "D1", "type": "led", "pins": {"anode": "VCC", "cathode": "LED_K"}},
                {"id": "R1", "type": "resistor", "value_ohms": None, "pins": {"1": "LED_K", "2": "GND"}}
            ]
        }
        res = self.verifier.verify(netlist)
        self.assertTrue(any(f["code"] == "LED_CURRENT_LIMITER_VALUE_UNKNOWN" for f in res["findings"]))
        self.assertEqual(res["status"], INDETERMINATE)

    def test_resistor_value_too_low(self):
        netlist = {
            "components": [
                {"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}},
                {"id": "D1", "type": "led", "pins": {"anode": "VCC", "cathode": "LED_K"}},
                {"id": "R1", "type": "resistor", "value_ohms": 10, "pins": {"1": "LED_K", "2": "GND"}}
            ]
        }
        res = self.verifier.verify(netlist)
        self.assertTrue(any(f["code"] == "LED_CURRENT_LIMITER_TOO_LOW" for f in res["findings"]))
        self.assertEqual(res["status"], FAIL)

if __name__ == '__main__':
    unittest.main()
