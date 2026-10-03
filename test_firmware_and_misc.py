"""Tests for firmware comment stripping, digital logic edge cases, and misc accuracy."""

import unittest
from logic.firmware import analyze_firmware, _strip_comments
from logic.digital_logic import DigitalLogicEvaluator
from logic.circuit_ir import CircuitIR


def _make_circuit(components, wires=None):
    """Create a CircuitIR from components and optional wires."""
    return CircuitIR({"components": components, "wires": wires or []})


class TestFirmwareCommentStripping(unittest.TestCase):
    """Verify that commented-out code is not parsed as live configuration."""

    def test_single_line_comment_stripped(self):
        source = '// pinMode(13, OUTPUT)\npinMode(12, INPUT);\n'
        result = analyze_firmware(source)
        self.assertNotIn("13", result["pins"])
        self.assertIn("12", result["pins"])

    def test_block_comment_stripped(self):
        source = '/* pinMode(13, OUTPUT); */\npinMode(12, INPUT);\n'
        result = analyze_firmware(source)
        self.assertNotIn("13", result["pins"])
        self.assertIn("12", result["pins"])

    def test_multiline_block_comment_stripped(self):
        source = '''/*
        pinMode(13, OUTPUT);
        digitalWrite(13, HIGH);
        */
        pinMode(12, INPUT);
        '''
        result = analyze_firmware(source)
        self.assertNotIn("13", result["pins"])
        self.assertIn("12", result["pins"])

    def test_inline_comment_after_code_preserved(self):
        source = 'pinMode(13, OUTPUT); // set LED pin\n'
        result = analyze_firmware(source)
        self.assertIn("13", result["pins"])
        self.assertEqual(result["pins"]["13"]["mode"], "OUTPUT")

    def test_commented_digital_write_stripped(self):
        source = '// digitalWrite(13, HIGH)\ndigitalWrite(12, LOW);\n'
        result = analyze_firmware(source)
        self.assertNotIn("13", result["pins"])
        self.assertIn("12", result["pins"])
        self.assertEqual(result["pins"]["12"]["digital_write"], "LOW")

    def test_commented_serial_begin_stripped(self):
        source = '// Serial.begin(9600)\nSerial.begin(115200);\n'
        result = analyze_firmware(source)
        self.assertEqual(result["protocols"]["serial_baud"], [115200])

    def test_commented_define_stripped(self):
        source = '// #define LED_PIN 13\n#define BTN_PIN 2\npinMode(BTN_PIN, INPUT);\n'
        result = analyze_firmware(source)
        self.assertNotIn("LED_PIN", result["pins"])
        self.assertIn("2", result["pins"])

    def test_mixed_comments_and_code(self):
        source = '''
        #define LED 13
        // #define MOTOR 9
        /* #define SENSOR A0 */
        pinMode(LED, OUTPUT);
        // pinMode(MOTOR, OUTPUT);
        /* pinMode(SENSOR, INPUT); */
        digitalWrite(LED, HIGH);
        '''
        result = analyze_firmware(source)
        pins = result["pins"]
        self.assertIn("13", pins)
        self.assertEqual(pins["13"]["mode"], "OUTPUT")
        self.assertEqual(pins["13"]["digital_write"], "HIGH")
        # MOTOR and SENSOR should NOT be parsed
        self.assertNotIn("MOTOR", pins)
        self.assertNotIn("9", pins)
        self.assertNotIn("SENSOR", pins)
        self.assertNotIn("A0", pins)

    def test_strip_comments_preserves_code(self):
        result = _strip_comments('int x = 5; // comment\nint y = 10;\n')
        self.assertIn("int x = 5;", result)
        self.assertIn("int y = 10;", result)
        self.assertNotIn("comment", result)

    def test_nested_block_comments(self):
        # C doesn't support nested block comments; first */ closes
        source = '/* outer /* inner */ pinMode(13, OUTPUT);\n'
        result = analyze_firmware(source)
        self.assertIn("13", result["pins"])

    def test_empty_comments_harmless(self):
        source = '//\n/**/\npinMode(13, OUTPUT);\n'
        result = analyze_firmware(source)
        self.assertIn("13", result["pins"])

    def test_pwm_in_comment_stripped(self):
        source = '// analogWrite(9, 128)\nanalogWrite(10, 255);\n'
        result = analyze_firmware(source)
        self.assertNotIn("9", result["pins"])
        self.assertIn("10", result["pins"])
        self.assertEqual(result["pins"]["10"]["pwm"], 255)

    def test_wire_begin_in_comment_stripped(self):
        source = '// Wire.begin()\nSPI.begin();\n'
        result = analyze_firmware(source)
        self.assertFalse(result["protocols"]["i2c"])
        self.assertTrue(result["protocols"]["spi"])


class TestDigitalLogicEdgeCases(unittest.TestCase):
    """Test digital logic evaluator edge cases."""

    def test_and_gate_true_true(self):
        circuit = _make_circuit([
            {"id": "G1", "type": "and_gate", "pins": {"A": "in1", "B": "in2", "Y": "out"}}
        ])
        evaluator = DigitalLogicEvaluator()
        result = evaluator.evaluate(circuit, initial_levels={"in1": True, "in2": True})
        self.assertEqual(result["levels"].get("out"), True)

    def test_and_gate_true_false(self):
        circuit = _make_circuit([
            {"id": "G1", "type": "and_gate", "pins": {"A": "in1", "B": "in2", "Y": "out"}}
        ])
        evaluator = DigitalLogicEvaluator()
        result = evaluator.evaluate(circuit, initial_levels={"in1": True, "in2": False})
        self.assertEqual(result["levels"].get("out"), False)

    def test_not_gate_inverts(self):
        circuit = _make_circuit([
            {"id": "G1", "type": "not_gate", "pins": {"A": "in1", "Y": "out"}}
        ])
        evaluator = DigitalLogicEvaluator()
        result = evaluator.evaluate(circuit, initial_levels={"in1": True})
        self.assertEqual(result["levels"].get("out"), False)

    def test_cascaded_gates(self):
        """NOT(AND(1,1)) = 0."""
        circuit = _make_circuit([
            {"id": "G1", "type": "and_gate", "pins": {"A": "a", "B": "b", "Y": "mid"}},
            {"id": "G2", "type": "not_gate", "pins": {"A": "mid", "Y": "out"}},
        ])
        evaluator = DigitalLogicEvaluator()
        result = evaluator.evaluate(circuit, initial_levels={"a": True, "b": True})
        self.assertEqual(result["levels"].get("out"), False)

    def test_or_gate(self):
        circuit = _make_circuit([
            {"id": "G1", "type": "or_gate", "pins": {"A": "a", "B": "b", "Y": "out"}}
        ])
        evaluator = DigitalLogicEvaluator()
        result = evaluator.evaluate(circuit, initial_levels={"a": False, "b": True})
        self.assertEqual(result["levels"].get("out"), True)

    def test_xor_gate(self):
        circuit = _make_circuit([
            {"id": "G1", "type": "xor_gate", "pins": {"A": "a", "B": "b", "Y": "out"}}
        ])
        evaluator = DigitalLogicEvaluator()
        result_same = evaluator.evaluate(circuit, initial_levels={"a": True, "b": True})
        self.assertEqual(result_same["levels"].get("out"), False)
        result_diff = evaluator.evaluate(circuit, initial_levels={"a": True, "b": False})
        self.assertEqual(result_diff["levels"].get("out"), True)

    def test_contention_detected(self):
        """Two gates driving the same net with different levels."""
        circuit = _make_circuit([
            {"id": "G1", "type": "buffer_gate", "pins": {"A": "a", "Y": "out"}},
            {"id": "G2", "type": "not_gate", "pins": {"A": "a", "Y": "out"}},
        ])
        evaluator = DigitalLogicEvaluator()
        result = evaluator.evaluate(circuit, initial_levels={"a": True})
        self.assertTrue(len(result.get("conflicts", [])) > 0)

    def test_no_gates_returns_clean(self):
        circuit = _make_circuit([
            {"id": "R1", "type": "resistor", "pins": {"1": "a", "2": "b"}}
        ])
        evaluator = DigitalLogicEvaluator()
        result = evaluator.evaluate(circuit)
        self.assertEqual(len(result.get("conflicts", [])), 0)

    def test_nand_gate(self):
        circuit = _make_circuit([
            {"id": "G1", "type": "nand_gate", "pins": {"A": "a", "B": "b", "Y": "out"}}
        ])
        evaluator = DigitalLogicEvaluator()
        result = evaluator.evaluate(circuit, initial_levels={"a": True, "b": True})
        self.assertEqual(result["levels"].get("out"), False)

    def test_nor_gate(self):
        circuit = _make_circuit([
            {"id": "G1", "type": "nor_gate", "pins": {"A": "a", "B": "b", "Y": "out"}}
        ])
        evaluator = DigitalLogicEvaluator()
        result = evaluator.evaluate(circuit, initial_levels={"a": False, "b": False})
        self.assertEqual(result["levels"].get("out"), True)


class TestCircuitIREdgeCases(unittest.TestCase):
    """Additional circuit IR edge cases."""

    def test_canonical_net_case_sensitive(self):
        """Net names are case-sensitive — GND != gnd without a wire."""
        circuit = _make_circuit([
            {"id": "R1", "type": "resistor", "pins": {"1": "GND", "2": "net1"}},
            {"id": "R2", "type": "resistor", "pins": {"1": "gnd", "2": "net2"}},
        ])
        # Without explicit wires, GND and gnd are different nets
        self.assertNotEqual(circuit.canonical_net("GND"), circuit.canonical_net("gnd"))

    def test_canonical_net_with_wire(self):
        """Wires merge nets."""
        circuit = _make_circuit([
            {"id": "R1", "type": "resistor", "pins": {"1": "a", "2": "b"}},
        ], [{"from": "a", "to": "c"}])
        self.assertEqual(circuit.canonical_net("a"), circuit.canonical_net("c"))

    def test_power_net_priority(self):
        """Power net names should be the canonical root."""
        circuit = _make_circuit([
            {"id": "R1", "type": "resistor", "pins": {"1": "random_net", "2": "x"}},
        ], [{"from": "random_net", "to": "GND"}])
        self.assertEqual(circuit.canonical_net("random_net"), "GND")

    def test_many_components(self):
        """Handle circuit with 20+ components without error."""
        components = [
            {"id": f"R{i}", "type": "resistor", "pins": {"1": f"net{i}", "2": f"net{i+1}"}}
            for i in range(20)
        ]
        circuit = _make_circuit(components)
        self.assertEqual(len(circuit.components), 20)

    def test_self_loop_wire_filtered(self):
        """Self-loop wires should be silently skipped."""
        circuit = _make_circuit([
            {"id": "R1", "type": "resistor", "pins": {"1": "a", "2": "b"}},
        ], [{"from": "a", "to": "a"}])
        self.assertEqual(circuit.canonical_net("a"), "a")

    def test_vcc_power_priority(self):
        """VCC stays canonical when merged with other nets."""
        circuit = _make_circuit([
            {"id": "R1", "type": "resistor", "pins": {"1": "x", "2": "y"}},
        ], [{"from": "x", "to": "VCC"}])
        self.assertEqual(circuit.canonical_net("x"), "VCC")

    def test_5v_power_priority(self):
        """5V stays canonical."""
        circuit = _make_circuit([
            {"id": "R1", "type": "resistor", "pins": {"1": "x", "2": "y"}},
        ], [{"from": "x", "to": "5V"}])
        self.assertEqual(circuit.canonical_net("x"), "5V")


    def test_tristate_buffer_enabled(self):
        circuit = _make_circuit([
            {"id": "G1", "type": "tristate_buffer", "pins": {"A": "a", "OE": "en", "Y": "out"}}
        ])
        evaluator = DigitalLogicEvaluator()
        result = evaluator.evaluate(circuit, initial_levels={"a": True, "en": True})
        self.assertEqual(result["levels"].get("out"), True)

    def test_tristate_buffer_disabled(self):
        circuit = _make_circuit([
            {"id": "G1", "type": "tristate_buffer", "pins": {"A": "a", "OE": "en", "Y": "out"}}
        ])
        evaluator = DigitalLogicEvaluator()
        result = evaluator.evaluate(circuit, initial_levels={"a": True, "en": False})
        self.assertNotIn("out", result["levels"])

    def test_open_drain_buffer(self):
        circuit = _make_circuit([
            {"id": "G1", "type": "open_drain_buffer", "pins": {"A": "a", "Y": "out"}}
        ])
        evaluator = DigitalLogicEvaluator()
        result_low = evaluator.evaluate(circuit, initial_levels={"a": True})
        self.assertEqual(result_low["levels"].get("out"), False)
        
        result_high_z = evaluator.evaluate(circuit, initial_levels={"a": False})
        self.assertNotIn("out", result_high_z["levels"])


from logic.digital_twin import DigitalTwinEngine

class TestPowerBudget(unittest.TestCase):
    def test_power_budget_exceeded(self):
        engine = DigitalTwinEngine()
        engine.specs = {
            "mcu": {"total_max_current_ma": 500},
            "motor": {"max_current_ma": 600}
        }
        circuit = _make_circuit([
            {"id": "U1", "type": "mcu", "pins": {"1": "net1"}},
            {"id": "M1", "type": "motor", "pins": {"1": "net2"}}
        ])
        result = engine.verify(circuit)
        self.assertTrue(any(f["code"] == "POWER_BUDGET_EXCEEDED" for f in result.get("findings", [])))

    def test_power_budget_ok(self):
        engine = DigitalTwinEngine()
        engine.specs = {
            "mcu": {"total_max_current_ma": 500},
            "sensor": {"typical_current_ma": 50}
        }
        circuit = _make_circuit([
            {"id": "U1", "type": "mcu", "pins": {"1": "net1"}},
            {"id": "M1", "type": "sensor", "pins": {"1": "net2"}}
        ])
        result = engine.verify(circuit)
        self.assertFalse(any(f["code"] == "POWER_BUDGET_EXCEEDED" for f in result.get("findings", [])))

if __name__ == '__main__':
    unittest.main()
