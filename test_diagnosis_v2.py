import unittest
from logic.diagnosis import FaultDiagnoser

class TestDiagnosisv2(unittest.TestCase):
    def setUp(self):
        self.diagnoser = FaultDiagnoser()
        
    def test_downstream_entries(self):
        self.assertGreaterEqual(len(self.diagnoser.DOWNSTREAM), 15)

    def test_led_reversed_polarity(self):
        findings = [
            {"code": "LED_REVERSED_POLARITY", "message": "Reversed LED"},
            {"code": "LED_NO_SOURCE_PATH", "message": "No source path"}
        ]
        res = self.diagnoser.diagnose(findings)
        primary = [f["code"] for f in res["primary_findings"]]
        secondary = [f["code"] for f in res["secondary_findings"]]
        self.assertIn("LED_REVERSED_POLARITY", primary)
        self.assertIn("LED_NO_SOURCE_PATH", secondary)
        
    def test_regulator_overvoltage(self):
        findings = [
            {"code": "REGULATOR_INPUT_OVERVOLTAGE", "message": "Overvoltage"},
            {"code": "I2C_DEVICE_NO_ACK", "message": "No ACK"}
        ]
        res = self.diagnoser.diagnose(findings)
        primary = [f["code"] for f in res["primary_findings"]]
        secondary = [f["code"] for f in res["secondary_findings"]]
        self.assertIn("REGULATOR_INPUT_OVERVOLTAGE", primary)
        self.assertIn("I2C_DEVICE_NO_ACK", secondary)

    def test_diagnosis_summary(self):
        res_0 = {"primary_findings": []}
        self.assertEqual(self.diagnoser.diagnosis_summary(res_0), "No faults detected. Your circuit looks good!")
        
        res_2 = {"primary_findings": [{"message": "Issue 1"}, {"message": "Issue 2"}]}
        summary_2 = self.diagnoser.diagnosis_summary(res_2)
        self.assertIn("Found 2 issue", summary_2)
        self.assertIn("1. Issue 1", summary_2)
        self.assertIn("2. Issue 2", summary_2)

if __name__ == '__main__':
    unittest.main()
