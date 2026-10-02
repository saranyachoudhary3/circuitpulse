import unittest
from logic.adc_analysis import ADCAnalyzer
from logic.circuit_ir import CircuitIR

class TestADCv2(unittest.TestCase):
    def test_adc_quantization(self):
        payload = {
            "components": [
                {"id": "U1", "type": "mcu", "pins": {"A0": "net1"}}
            ],
            "measurements": {
                "adc": {"A0": 512}
            }
        }
        circuit = CircuitIR(payload)
        rule = {
            "channel": "A0",
            "reference_voltage_v": 5.0,
            "input_voltage_range_v": [0.0, 5.0],
            "resolution_bits": 10,
            "expected_voltage_range_v": [2.49, 2.51]
        }
        analyzer = ADCAnalyzer()
        findings = analyzer.evaluate(circuit, rule)
        out_of_range = [f for f in findings if f["code"] == "ADC_MEASUREMENT_OUT_OF_RANGE"]
        self.assertEqual(len(out_of_range), 0)

        rule2 = {
            "channel": "A0",
            "reference_voltage_v": 5.0,
            "input_voltage_range_v": [0.0, 5.0],
            "resolution_bits": 10,
            "expected_voltage_range_v": [2.51, 2.52]
        }
        findings2 = analyzer.evaluate(circuit, rule2)
        out_of_range2 = [f for f in findings2 if f["code"] == "ADC_MEASUREMENT_OUT_OF_RANGE"]
        self.assertEqual(len(out_of_range2), 1)
        self.assertAlmostEqual(out_of_range2[0]["evidence"]["derived_voltage_v"], 2.5)

if __name__ == '__main__':
    unittest.main()
