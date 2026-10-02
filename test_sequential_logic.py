import unittest

from logic.logic_engine import CircuitLogicEngine


class SequentialLogicTests(unittest.TestCase):
    def test_d_flip_flop_follows_d_on_rising_edge(self):
        circuit = {
            "components": [
                {"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}},
                {"id": "FF1", "type": "d_flip_flop", "pins": {"D": "D", "CLK": "CLK", "Q": "Q"}, "initial_q": 0},
            ],
            "measurements": {"digital_trace": [
                {"time_us": 0, "levels": {"D": 0, "CLK": 0}},
                {"time_us": 10, "levels": {"D": 1}},
                {"time_us": 20, "levels": {"CLK": 1}},
            ]},
            "requirements": [{"kind": "sequential_logic", "expected_final_levels": {"Q": 1}}],
        }
        result = CircuitLogicEngine().analyze(circuit)
        self.assertEqual(result["status"], "PASS")

    def test_jk_flip_flop_requires_known_initial_state(self):
        circuit = {
            "components": [
                {"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}},
                {"id": "FF1", "type": "jk_flip_flop", "pins": {"J": "J", "K": "K", "CLK": "CLK", "Q": "Q"}},
            ],
            "measurements": {"digital_trace": [
                {"time_us": 0, "levels": {"J": 1, "K": 1, "CLK": 0}},
                {"time_us": 10, "levels": {"CLK": 1}},
            ]},
            "requirements": [{"kind": "sequential_logic", "expected_final_levels": {"Q": 0}}],
        }
        result = CircuitLogicEngine().analyze(circuit)
        codes = {item["code"] for item in result["findings"]}
        self.assertEqual(result["status"], "INDETERMINATE")
        self.assertIn("SEQUENTIAL_INPUT_UNRESOLVED", codes)

    def test_reset_dominates_clocked_state(self):
        circuit = {
            "components": [
                {"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}},
                {"id": "FF1", "type": "d_flip_flop", "pins": {"D": "D", "CLK": "CLK", "Q": "Q", "CLR": "CLR"},
                 "initial_q": 1, "reset_pin": "CLR", "reset_active": 0},
            ],
            "measurements": {"digital_trace": [{"time_us": 0, "levels": {"D": 1, "CLK": 0, "CLR": 0}}]},
            "requirements": [{"kind": "sequential_logic", "expected_final_levels": {"Q": 0}}],
        }
        self.assertEqual(CircuitLogicEngine().analyze(circuit)["status"], "PASS")

    def test_setup_time_violation_is_a_critical_fault(self):
        circuit = {
            "components": [
                {"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}},
                {"id": "FF1", "type": "d_flip_flop", "pins": {"D": "D", "CLK": "CLK", "Q": "Q"}, "initial_q": 0,
                 "setup_time_us": 5},
            ],
            "measurements": {"digital_trace": [
                {"time_us": 0, "levels": {"D": 0, "CLK": 0}},
                {"time_us": 10, "levels": {"D": 1}},
                {"time_us": 12, "levels": {"CLK": 1}},
            ]},
            "requirements": [{"kind": "sequential_logic", "expected_final_levels": {"Q": 1}}],
        }
        result = CircuitLogicEngine().analyze(circuit)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("SEQUENTIAL_SETUP_TIME_VIOLATION", {item["code"] for item in result["findings"]})
