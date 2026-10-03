import unittest
from logic.circuit_ir import CircuitIR
from logic.digital_logic import DigitalLogicEvaluator

class TestOpenDrain(unittest.TestCase):
    def test_open_drain_with_pullup(self):
        payload = {
            "components": [
                {
                    "id": "od1",
                    "type": "open_drain_buffer",
                    "pins": {"A": "in_net", "Y": "out_net"}
                }
            ]
        }
        circuit = CircuitIR(payload)
        
        evaluator = DigitalLogicEvaluator()
        # Initial levels: pull-up resistor on out_net (True), and input is True
        initial_levels = {"out_net": True, "in_net": True}
        result = evaluator.evaluate(circuit, initial_levels=initial_levels)
        
        self.assertEqual(result["status"], "PASS")
        self.assertNotIn("od1", result["conflicts"])
        self.assertEqual(result["levels"]["out_net"], 0)

if __name__ == '__main__':
    unittest.main()
