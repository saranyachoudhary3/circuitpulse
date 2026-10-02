import unittest

from logic.logic_engine import CircuitLogicEngine
from logic.catalog import PresetCatalog
from logic.repair_planner import RepairPlanner


class TypedCircuitLogicTests(unittest.TestCase):
    def setUp(self):
        self.engine = CircuitLogicEngine()

    def test_voltage_divider_out_of_range_is_a_critical_fault(self):
        circuit = {
            "components": [
                {"id": "SUPPLY", "type": "supply", "pins": {"positive": "VIN", "negative": "GND"}},
                {"id": "R1", "type": "resistor", "value_ohms": 1000, "pins": {"1": "VIN", "2": "A0"}},
                {"id": "R2", "type": "resistor", "value_ohms": 10000, "pins": {"1": "A0", "2": "GND"}},
            ],
            "requirements": [{"kind": "voltage_divider", "upper_resistor": "R1", "lower_resistor": "R2",
                              "input_voltage_v": 5, "output_net": "A0", "output_max_v": 3.3}],
        }
        result = self.engine.analyze(circuit)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("DIVIDER_OUTPUT_OUT_OF_RANGE", {item["code"] for item in result["findings"]})

    def test_protocol_and_operating_faults_are_ranked(self):
        circuit = {
            "components": [
                {"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}},
                {"id": "RP1", "type": "resistor", "value_ohms": 4700, "pins": {"1": "VCC", "2": "SDA"}},
                {"id": "RP2", "type": "resistor", "value_ohms": 4700, "pins": {"1": "VCC", "2": "SCL"}},
            ],
            "requirements": [
                {"kind": "i2c", "sda_net": "SDA", "scl_net": "SCL", "supply_net": "VCC", "pullup_resistors": ["RP1", "RP2"]},
                {"kind": "gpio_output", "component_id": "MCU:D13", "load_current_ma": 50, "max_current_ma": 20},
                {"kind": "inductive_load", "component_id": "M1", "flyback_protection": False},
            ],
        }
        result = self.engine.analyze(circuit)
        self.assertEqual(result["status"], "FAIL")
        codes = {item["code"] for item in result["findings"]}
        self.assertTrue({"GPIO_CURRENT_LIMIT_EXCEEDED", "FLYBACK_PROTECTION_MISSING"}.issubset(codes))
        self.assertEqual(result["root_causes"][0]["severity"], "critical")
        self.assertIn("transistor or driver", next(item for item in result["root_causes"] if item["code"] == "GPIO_CURRENT_LIMIT_EXCEEDED")["recommended_action"])

    def test_resistor_power_rating_is_checked_when_voltage_is_measured(self):
        circuit = {
            "components": [
                {"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}},
                {"id": "R1", "type": "resistor", "value_ohms": 100, "power_rating_w": 0.25, "voltage_across_v": 12,
                 "pins": {"1": "VCC", "2": "GND"}},
            ]
        }
        result = self.engine.analyze(circuit)
        self.assertIn("RESISTOR_POWER_EXCEEDED", {item["code"] for item in result["findings"]})

    def test_current_budget_and_op_amp_envelopes_fail_before_power_up(self):
        circuit = {
            "components": [{"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}}],
            "requirements": [
                {"kind": "current_budget", "source_id": "USB", "available_current_ma": 500, "derating_fraction": 0.8,
                 "loads": [{"component_id": "servo", "current_ma": 300}, {"component_id": "motor", "current_ma": 200}]},
                {"kind": "op_amp_operating_point", "component_id": "U1", "noninverting_voltage_v": 4.8,
                 "inverting_voltage_v": 1.0, "common_mode_min_v": 0, "common_mode_max_v": 3.5,
                 "expected_output_v": 1.0, "output_min_v": 0.1, "output_max_v": 4.5},
            ],
        }
        codes = {item["code"] for item in self.engine.analyze(circuit)["findings"]}
        self.assertTrue({"CURRENT_BUDGET_EXCEEDED", "OP_AMP_COMMON_MODE_OUT_OF_RANGE"}.issubset(codes))

    def test_firmware_contract_binds_literal_output_to_captured_signal(self):
        circuit = {
            "components": [{"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}}],
            "measurements": {"digital_trace": [{"time_us": 0, "levels": {"LED_NET": 0}}]},
            "requirements": [{"kind": "firmware_contract", "source": "pinMode(D13, OUTPUT); digitalWrite(D13, HIGH); Wire.begin();",
                              "expected_pins": {"D13": {"mode": "OUTPUT"}}, "required_protocols": {"i2c": True},
                              "signal_nets": {"D13": "LED_NET"}}],
        }
        result = self.engine.analyze(circuit)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("FIRMWARE_TRACE_MISMATCH", {item["code"] for item in result["findings"]})

    def test_causal_diagnosis_marks_protocol_symptom_secondary_to_power_fault(self):
        circuit = {
            "components": [{"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}}],
            "measurements": {"i2c_addresses": []},
            "requirements": [
                {"kind": "power_domain", "component_id": "sensor", "supply_voltage_v": 5, "min_voltage_v": 3, "max_voltage_v": 3.6},
                {"kind": "i2c_ack", "address": "0x76"},
            ],
        }
        result = self.engine.analyze(circuit)
        self.assertEqual([item["code"] for item in result["diagnosis"]["primary_findings"]], ["POWER_DOMAIN_OUT_OF_RANGE"])
        self.assertEqual([item["code"] for item in result["diagnosis"]["secondary_findings"]], ["I2C_DEVICE_NO_ACK"])

    def test_worst_case_divider_and_rc_tolerances_are_enforced(self):
        circuit = {
            "components": [
                {"id": "SUPPLY", "type": "supply", "pins": {"positive": "VIN", "negative": "GND"}},
                {"id": "R1", "type": "resistor", "value_ohms": 1000, "tolerance_fraction": 0.05, "pins": {"1": "VIN", "2": "A0"}},
                {"id": "R2", "type": "resistor", "value_ohms": 1000, "tolerance_fraction": 0.05, "pins": {"1": "A0", "2": "GND"}},
                {"id": "C1", "type": "capacitor", "value_uf": 100, "tolerance_fraction": 0.2, "pins": {"1": "A0", "2": "GND"}},
            ],
            "requirements": [
                {"kind": "voltage_divider_tolerance", "upper_resistor": "R1", "lower_resistor": "R2",
                 "input_voltage_range_v": [4.75, 5.25], "output_voltage_range_v": [2.45, 2.55]},
                {"kind": "rc_tolerance", "resistor": "R1", "capacitor": "C1", "tau_range_ms": [95, 105]},
            ],
        }
        codes = {item["code"] for item in self.engine.analyze(circuit)["findings"]}
        self.assertTrue({"DIVIDER_TOLERANCE_OUT_OF_RANGE", "RC_TOLERANCE_OUT_OF_RANGE"}.issubset(codes))

    def test_power_sequence_rejects_enable_before_power_good(self):
        circuit = {
            "components": [{"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}}],
            "measurements": {"voltage_trace": [
                {"time_us": 0, "voltages_v": {"VCC": 0, "EN": 0}},
                {"time_us": 5, "voltages_v": {"EN": 1}},
                {"time_us": 10, "voltages_v": {"VCC": 3.3}},
            ]},
            "requirements": [{"kind": "power_sequence", "power_net": "VCC", "power_good_threshold_v": 3,
                              "signals": [{"net": "EN", "threshold_v": 0.5, "min_after_power_good_us": 2}]}],
        }
        result = self.engine.analyze(circuit)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("POWER_SEQUENCE_ORDER_VIOLATION", {item["code"] for item in result["findings"]})

    def test_adc_reference_and_raw_code_limits_are_checked(self):
        circuit = {
            "components": [{"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}}],
            "measurements": {"adc": {"A0": 900}},
            "requirements": [{"kind": "adc", "channel": "A0", "reference_voltage_v": 3.3,
                              "input_voltage_range_v": [0, 5], "resolution_bits": 10,
                              "expected_voltage_range_v": [0, 2]}],
        }
        codes = {item["code"] for item in self.engine.analyze(circuit)["findings"]}
        self.assertTrue({"ADC_INPUT_OVERVOLTAGE", "ADC_MEASUREMENT_OUT_OF_RANGE"}.issubset(codes))

    def test_clock_frequency_jitter_and_duty_are_checked_from_trace(self):
        circuit = {
            "components": [{"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}}],
            "measurements": {"digital_trace": [
                {"time_us": 0, "levels": {"CLK": 0}}, {"time_us": 1, "levels": {"CLK": 1}},
                {"time_us": 8, "levels": {"CLK": 0}}, {"time_us": 11, "levels": {"CLK": 1}},
                {"time_us": 18, "levels": {"CLK": 0}}, {"time_us": 20, "levels": {"CLK": 1}},
            ]},
            "requirements": [{"kind": "clock_timing", "clock_net": "CLK", "frequency_range_hz": [100000, 104000],
                              "max_period_jitter_us": 0.4, "duty_cycle_range": [0.4, 0.6]}],
        }
        codes = {item["code"] for item in self.engine.analyze(circuit)["findings"]}
        self.assertTrue({"CLOCK_FREQUENCY_OUT_OF_RANGE", "CLOCK_JITTER_EXCEEDED", "CLOCK_DUTY_OUT_OF_RANGE"}.issubset(codes))

    def test_thermal_derating_blocks_overheated_driver(self):
        circuit = {
            "components": [{"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}}],
            "requirements": [{"kind": "thermal", "component_id": "MOTOR_DRIVER", "dissipation_w": 1.3, "ambient_c": 35,
                              "theta_ja_c_per_w": 60, "max_junction_c": 125, "derating_fraction": 0.8}],
        }
        result = self.engine.analyze(circuit)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("THERMAL_DERATING_EXCEEDED", {item["code"] for item in result["findings"]})

    def test_truth_table_checks_all_declared_combinational_inputs(self):
        circuit = {
            "components": [
                {"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}},
                {"id": "U1", "type": "xor_gate", "pins": {"A": "A", "B": "B", "Y": "Y"}},
            ],
            "requirements": [{"kind": "digital_truth_table", "input_nets": ["A", "B"], "output_net": "Y", "rows": [
                {"inputs": {"A": 0, "B": 0}, "output": 0}, {"inputs": {"A": 0, "B": 1}, "output": 1},
                {"inputs": {"A": 1, "B": 0}, "output": 1}, {"inputs": {"A": 1, "B": 1}, "output": 1},
            ]}],
        }
        result = self.engine.analyze(circuit)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("TRUTH_TABLE_MISMATCH", {item["code"] for item in result["findings"]})

    def test_temporal_assertion_detects_missing_sensor_response(self):
        circuit = {
            "components": [{"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}}],
            "measurements": {"digital_trace": [
                {"time_us": 0, "levels": {"TRIG": 0, "ECHO": 0}}, {"time_us": 10, "levels": {"TRIG": 1}},
                {"time_us": 20, "levels": {"TRIG": 0}}, {"time_us": 200, "levels": {"ECHO": 1}},
            ]},
            "requirements": [{"kind": "temporal_assertion", "trigger_net": "TRIG", "response_net": "ECHO",
                              "min_delay_us": 5, "max_delay_us": 100}],
        }
        result = self.engine.analyze(circuit)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("TEMPORAL_RESPONSE_TIMEOUT", {item["code"] for item in result["findings"]})

    def test_state_machine_trace_rejects_wrong_clocked_transition(self):
        circuit = {
            "components": [{"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}}],
            "measurements": {"digital_trace": [
                {"time_us": 0, "levels": {"CLK": 0, "Q": 0, "X": 1}},
                {"time_us": 10, "levels": {"CLK": 1}}, {"time_us": 12, "levels": {"Q": 0}},
            ]},
            "requirements": [{"kind": "state_machine_trace", "clock_net": "CLK", "state_nets": ["Q"], "input_nets": ["X"], "settle_max_us": 5,
                              "transitions": [{"state": {"Q": 0}, "inputs": {"X": 1}, "next_state": {"Q": 1}}]}],
        }
        result = self.engine.analyze(circuit)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("STATE_MACHINE_TRANSITION_MISMATCH", {item["code"] for item in result["findings"]})

    def test_spi_signals_must_be_electrically_distinct(self):
        circuit = {
            "components": [{"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}}],
            "requirements": [{"kind": "spi", "signals": {"mosi": "MOSI", "miso": "MISO", "sck": "CLK", "cs": "CLK"}}],
        }
        result = self.engine.analyze(circuit)
        self.assertIn("SPI_SIGNAL_SHORT", {item["code"] for item in result["findings"]})

    def test_internal_dc_solver_detects_out_of_range_node(self):
        circuit = {
            "components": [
                {"id": "V1", "type": "voltage_source", "voltage_v": 5, "pins": {"positive": "VIN", "negative": "GND"}},
                {"id": "R1", "type": "resistor", "value_ohms": 1000, "pins": {"1": "VIN", "2": "A0"}},
                {"id": "R2", "type": "resistor", "value_ohms": 1000, "pins": {"1": "A0", "2": "GND"}},
            ],
            "requirements": [{"kind": "dc_operating_point", "ground_net": "GND", "expected_node_ranges": {"A0": [0, 2]}}],
        }
        result = self.engine.analyze(circuit)
        finding = next(item for item in result["findings"] if item["code"] == "DC_NODE_OUT_OF_RANGE")
        self.assertAlmostEqual(finding["evidence"]["voltage_v"], 2.5, places=4)

    def test_combinational_logic_mismatch_is_reported(self):
        circuit = {
            "components": [
                {"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}},
                {"id": "A", "type": "logic_input", "level": 1, "pins": {"OUT": "A"}},
                {"id": "B", "type": "logic_input", "level": 0, "pins": {"OUT": "B"}},
                {"id": "G1", "type": "and_gate", "pins": {"A": "A", "B": "B", "Y": "Y"}},
            ],
            "requirements": [{"kind": "digital_logic", "expected_levels": {"Y": 1}}],
        }
        result = self.engine.analyze(circuit)
        self.assertIn("DIGITAL_EXPECTATION_MISMATCH", {item["code"] for item in result["findings"]})

    def test_power_domain_and_uart_faults(self):
        circuit = {
            "components": [{"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}}],
            "requirements": [
                {"kind": "power_domain", "component_id": "RC522", "supply_voltage_v": 5, "min_voltage_v": 3.0, "max_voltage_v": 3.6},
                {"kind": "uart", "tx_net": "UART", "rx_net": "UART", "require_common_ground": True, "ground_net": "GND"},
            ],
        }
        result = self.engine.analyze(circuit)
        codes = {item["code"] for item in result["findings"]}
        self.assertTrue({"POWER_DOMAIN_OUT_OF_RANGE", "UART_LINES_SHORTED"}.issubset(codes))

    def test_rc_timing_detects_wrong_delay_value(self):
        circuit = {
            "components": [
                {"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}},
                {"id": "R1", "type": "resistor", "value_ohms": 1000, "pins": {"1": "VCC", "2": "RC"}},
                {"id": "C1", "type": "capacitor", "value_uf": 1, "pins": {"1": "RC", "2": "GND"}},
            ],
            "requirements": [{"kind": "rc_timing", "resistor": "R1", "capacitor": "C1", "tau_range_ms": [2, 3]}],
        }
        result = self.engine.analyze(circuit)
        self.assertIn("RC_TIME_OUT_OF_RANGE", {item["code"] for item in result["findings"]})

    def test_measured_pwm_and_i2c_runtime_faults_are_detected(self):
        circuit = {
            "components": [{"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}}],
            "measurements": {"pwm": {"D9": {"frequency_hz": 100, "duty_cycle": 0.9}}, "i2c_addresses": ["0x76"]},
            "requirements": [
                {"kind": "pwm", "signal": "D9", "frequency_min_hz": 400, "frequency_max_hz": 600, "duty_min": 0.1, "duty_max": 0.8},
                {"kind": "i2c_ack", "address": "0x77"},
            ],
        }
        result = self.engine.analyze(circuit)
        codes = {item["code"] for item in result["findings"]}
        self.assertTrue({"PWM_OUT_OF_RANGE", "I2C_DEVICE_NO_ACK"}.issubset(codes))

    def test_level_regulator_and_mosfet_driver_faults_are_detected(self):
        circuit = {
            "components": [{"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}}],
            "requirements": [
                {"kind": "logic_level_interface", "component_id": "RC522", "source_high_v": 5, "destination_max_v": 3.6},
                {"kind": "regulator", "component_id": "U1", "input_voltage_v": 3.5, "output_voltage_v": 3.3, "dropout_v": 0.5, "max_input_voltage_v": 12},
                {"kind": "transistor_driver", "device": "mosfet", "component_id": "Q1", "load_current_ma": 100, "rated_current_ma": 500,
                 "gate_drive_v": 3.3, "required_gate_drive_v": 4.5},
            ],
        }
        codes = {item["code"] for item in self.engine.analyze(circuit)["findings"]}
        self.assertTrue({"LOGIC_LEVEL_OVERVOLTAGE", "REGULATOR_DROPOUT", "MOSFET_GATE_UNDERDRIVEN"}.issubset(codes))

    def test_repair_planner_removes_short_before_adding_missing_wires(self):
        preset = PresetCatalog().get("led_blink")
        plan = RepairPlanner().plan(preset, [{"from": "arduino:5V", "to": "arduino:GND"}])
        self.assertEqual(plan["next_action"]["kind"], "remove")
        self.assertEqual(plan["next_action"]["priority"], 0)
        self.assertEqual(plan["actions"][1]["kind"], "add")

    def test_repair_planner_includes_typed_electrical_action(self):
        plan = RepairPlanner().plan(PresetCatalog().get("led_blink"), [], [{
            "code": "GPIO_CURRENT_LIMIT_EXCEEDED", "severity": "critical", "message": "GPIO load is too high.",
            "recommended_action": "Move the load to a driver.",
        }])
        electrical = next(item for item in plan["actions"] if item["kind"] == "electrical_repair")
        self.assertEqual(electrical["instruction"], "Move the load to a driver.")


if __name__ == "__main__":
    unittest.main()
