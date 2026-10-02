import unittest

from logic.netlist import FAIL, INDETERMINATE, PASS, NetlistError, NetlistVerifier


GOOD_LED = {
    "components": [
        {"id": "PS1", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}},
        {"id": "R1", "type": "resistor", "value_ohms": 220, "pins": {"1": "VCC", "2": "LED_A"}},
        {"id": "D1", "type": "led", "pins": {"anode": "LED_A", "cathode": "GND"}},
    ]
}


class NetlistVerifierTests(unittest.TestCase):
    def setUp(self):
        self.verifier = NetlistVerifier()

    def test_led_with_series_resistor_passes(self):
        report = self.verifier.verify(GOOD_LED)
        self.assertEqual(report["status"], PASS)
        self.assertEqual(report["findings"], [])

    def test_power_ground_zero_ohm_path_fails(self):
        circuit = {**GOOD_LED, "wires": [{"from": "VCC", "to": "GND"}]}
        report = self.verifier.verify(circuit)
        self.assertEqual(report["status"], FAIL)
        self.assertIn("DIRECT_POWER_SHORT", {item["code"] for item in report["findings"]})

    def test_led_without_resistor_fails(self):
        circuit = {
            "components": [
                {"id": "PS1", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}},
                {"id": "D1", "type": "led", "pins": {"anode": "VCC", "cathode": "GND"}},
            ]
        }
        report = self.verifier.verify(circuit)
        self.assertEqual(report["status"], FAIL)
        self.assertIn("LED_CURRENT_LIMITER_MISSING", {item["code"] for item in report["findings"]})

    def test_undersized_led_resistor_fails(self):
        circuit = {
            "components": [
                {"id": "PS1", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}},
                {"id": "R1", "type": "resistor", "value_ohms": 10, "pins": {"1": "VCC", "2": "LED_A"}},
                {"id": "D1", "type": "led", "pins": {"anode": "LED_A", "cathode": "GND"}},
            ]
        }
        report = self.verifier.verify(circuit)
        self.assertEqual(report["status"], FAIL)
        self.assertIn("LED_CURRENT_LIMITER_TOO_LOW", {item["code"] for item in report["findings"]})

    def test_missing_supply_is_indeterminate(self):
        report = self.verifier.verify({"components": [{"id": "D1", "type": "led", "pins": {"anode": "A", "cathode": "B"}}]})
        self.assertEqual(report["status"], INDETERMINATE)

    def test_rejects_duplicate_ids(self):
        with self.assertRaises(NetlistError):
            self.verifier.verify({"components": [
                {"id": "R1", "type": "resistor", "pins": {"1": "A", "2": "B"}},
                {"id": "R1", "type": "resistor", "pins": {"1": "C", "2": "D"}},
            ]})


if __name__ == "__main__":
    unittest.main()
