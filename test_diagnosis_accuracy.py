import unittest

from logic.diagnosis import FaultDiagnoser


class TestDiagnosisAccuracy(unittest.TestCase):
    def setUp(self):
        self.diagnoser = FaultDiagnoser()

    def test_single_fault(self):
        findings = [{"code": "DIRECT_POWER_SHORT", "message": "Short!"}]
        res = self.diagnoser.diagnose(findings)
        self.assertEqual(len(res["primary_findings"]), 1)
        self.assertEqual(len(res["secondary_findings"]), 0)

    def test_power_short_masks_i2c(self):
        findings = [
            {"code": "DIRECT_POWER_SHORT", "message": "Short!"},
            {"code": "I2C_DEVICE_NO_ACK", "message": "No ACK"}
        ]
        res = self.diagnoser.diagnose(findings)
        self.assertEqual(len(res["primary_findings"]), 1)
        self.assertEqual(res["primary_findings"][0]["code"], "DIRECT_POWER_SHORT")
        self.assertEqual(len(res["secondary_findings"]), 1)
        self.assertEqual(res["secondary_findings"][0]["code"], "I2C_DEVICE_NO_ACK")

    def test_multiple_independent_faults(self):
        findings = [
            {"code": "LED_CURRENT_LIMITER_MISSING", "message": "No resistor"},
            {"code": "GPIO_CURRENT_LIMIT_EXCEEDED", "message": "Too much current"}
        ]
        res = self.diagnoser.diagnose(findings)
        self.assertEqual(len(res["primary_findings"]), 2)
        self.assertEqual(len(res["secondary_findings"]), 0)

    def test_cascading_fault_chain(self):
        findings = [
            {"code": "REGULATOR_DROPOUT", "message": "Regulator issue"},
            {"code": "POWER_DOMAIN_OUT_OF_RANGE", "message": "Voltage wrong"},
            {"code": "I2C_DEVICE_NO_ACK", "message": "No ACK"}
        ]
        # Currently, the diagnostic engine maps direct cause->effect.
        # REGULATOR_DROPOUT explains I2C_DEVICE_NO_ACK
        # Let's verify standard resolution.
        res = self.diagnoser.diagnose(findings)
        primary_codes = {f["code"] for f in res["primary_findings"]}
        secondary_codes = {f["code"] for f in res["secondary_findings"]}
        self.assertIn("REGULATOR_DROPOUT", primary_codes)
        self.assertIn("I2C_DEVICE_NO_ACK", secondary_codes)

    def test_all_downstream_rules(self):
        for cause, effects in FaultDiagnoser.DOWNSTREAM.items():
            for effect in effects:
                res = self.diagnoser.diagnose([{"code": cause}, {"code": effect}])
                self.assertEqual(res["primary_findings"][0]["code"], cause)
                self.assertEqual(res["secondary_findings"][0]["code"], effect)

    def test_no_false_attribution(self):
        res = self.diagnoser.diagnose([{"code": "I2C_LINES_SHORTED"}, {"code": "UART_TRACE_NO_FRAME"}])
        self.assertEqual(len(res["primary_findings"]), 2)
        self.assertEqual(len(res["secondary_findings"]), 0)

    def test_diagnosis_summary_0_findings(self):
        res = self.diagnoser.diagnose([])
        summary = self.diagnoser.diagnosis_summary(res)
        self.assertIn("No faults detected", summary)

    def test_diagnosis_summary_1_finding(self):
        res = self.diagnoser.diagnose([{"code": "DIRECT_POWER_SHORT", "message": "Short!"}])
        summary = self.diagnoser.diagnosis_summary(res)
        self.assertIn("Found 1 issue", summary)
        self.assertIn("Short!", summary)

    def test_diagnosis_summary_5_findings(self):
        findings = [{"code": f"F{i}", "message": f"M{i}"} for i in range(5)]
        res = self.diagnoser.diagnose(findings)
        summary = self.diagnoser.diagnosis_summary(res)
        self.assertIn("Found 5 issue", summary)
        self.assertEqual(summary.count("\n"), 3)

    def test_empty_findings_list(self):
        res = self.diagnoser.diagnose([])
        self.assertEqual(len(res["primary_findings"]), 0)

    def test_unknown_fault_code(self):
        res = self.diagnoser.diagnose([{"code": "UNKNOWN_CODE", "message": "???"}])
        self.assertEqual(len(res["primary_findings"]), 1)
        self.assertEqual(res["primary_findings"][0]["code"], "UNKNOWN_CODE")

    def test_led_reversed_causes_no_source_path_secondary(self):
        res = self.diagnoser.diagnose([{"code": "LED_REVERSED_POLARITY"}, {"code": "LED_NO_SOURCE_PATH"}])
        self.assertEqual(res["primary_findings"][0]["code"], "LED_REVERSED_POLARITY")
        self.assertEqual(res["secondary_findings"][0]["code"], "LED_NO_SOURCE_PATH")

    def test_component_self_short_causes_dc_node_secondary(self):
        res = self.diagnoser.diagnose([{"code": "COMPONENT_SELF_SHORT"}, {"code": "DC_NODE_OUT_OF_RANGE"}])
        self.assertEqual(res["primary_findings"][0]["code"], "COMPONENT_SELF_SHORT")
        self.assertEqual(res["secondary_findings"][0]["code"], "DC_NODE_OUT_OF_RANGE")

    def test_mosfet_gate_causes_firmware_secondary(self):
        res = self.diagnoser.diagnose([{"code": "MOSFET_GATE_UNDERDRIVEN"}, {"code": "FIRMWARE_TRACE_MISMATCH"}])
        self.assertEqual(res["primary_findings"][0]["code"], "MOSFET_GATE_UNDERDRIVEN")
        self.assertEqual(res["secondary_findings"][0]["code"], "FIRMWARE_TRACE_MISMATCH")

    def test_mixed_critical_warning_findings(self):
        # Ranking is done in logic_engine, but we can verify diagnosis engine passes through the rank order
        findings = [{"code": "A", "severity": "warning"}, {"code": "B", "severity": "critical"}]
        res = self.diagnoser.diagnose(findings)
        self.assertEqual(res["primary_findings"], [{"code": "A", "severity": "warning", "diagnostic_role": "primary_or_independent"},
                                                   {"code": "B", "severity": "critical", "diagnostic_role": "primary_or_independent"}])


if __name__ == '__main__':
    unittest.main()
