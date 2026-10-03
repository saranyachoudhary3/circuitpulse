import unittest
from typing import Any

from logic.logic_engine import CircuitLogicEngine
from logic.circuit_ir import CircuitIRError


class TestRealisticCircuits(unittest.TestCase):
    def setUp(self):
        self.engine = CircuitLogicEngine()

    def run_engine(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.engine.analyze(payload)

    # Correct Circuits
    def test_simple_led_circuit(self):
        payload = {
            "schema_version": 1,
            "components": [
                {"id": "MCU1", "type": "arduino", "pins": {"13": "net3", "GND": "net2", "5V": "net1_supply"}},
                {"id": "D1", "type": "led", "pins": {"anode": "net1", "cathode": "net2"}},
                {"id": "R1", "type": "resistor", "value_ohms": 220, "pins": {"1": "net1", "2": "net3"}}
            ],
            "wires": [{"from": "net1_supply", "to": "net1"}],
            "requirements": []
        }
        res = self.run_engine(payload)
        self.assertEqual(res["status"], "PASS")

    def test_dual_led_circuit(self):
        payload = {
            "schema_version": 1,
            "components": [
                {"id": "MCU1", "type": "arduino", "pins": {"13": "net1", "12": "net2", "GND": "gnd", "5V": "vcc"}},
                {"id": "D1", "type": "led", "pins": {"anode": "net3", "cathode": "gnd"}},
                {"id": "R1", "type": "resistor", "value_ohms": 220, "pins": {"1": "net1", "2": "net3"}},
                {"id": "D2", "type": "led", "pins": {"anode": "net4", "cathode": "gnd"}},
                {"id": "R2", "type": "resistor", "value_ohms": 220, "pins": {"1": "net2", "2": "net4"}}
            ],
            "wires": [{"from": "vcc", "to": "net1"}, {"from": "vcc", "to": "net2"}],
            "requirements": []
        }
        res = self.run_engine(payload)
        self.assertIn(res["status"], ["PASS", "INDETERMINATE"])

    def test_button_input_with_pullup(self):
        payload = {
            "schema_version": 1,
            "components": [
                {"id": "MCU1", "type": "arduino", "pins": {"2": "button_net", "GND": "gnd", "5V": "vcc"}},
                {"id": "SW1", "type": "button", "pins": {"1": "button_net", "2": "gnd"}},
                {"id": "R1", "type": "resistor", "value_ohms": 10000, "pins": {"1": "vcc", "2": "button_net"}}
            ],
            "wires": [],
            "requirements": []
        }
        res = self.run_engine(payload)
        self.assertNotIn("FLOATING_INPUT", [f["code"] for f in res["findings"]])

    def test_voltage_divider_sensor(self):
        payload = {
            "schema_version": 1,
            "components": [
                {"id": "V1", "type": "supply", "pins": {"positive": "vcc", "negative": "gnd"}},
                {"id": "R1", "type": "resistor", "value_ohms": 10000, "pins": {"1": "vcc", "2": "mid"}},
                {"id": "R2", "type": "resistor", "value_ohms": 10000, "pins": {"1": "mid", "2": "gnd"}}
            ],
            "wires": [],
            "requirements": [{
                "kind": "voltage_divider",
                "upper_resistor": "R1",
                "lower_resistor": "R2",
                "input_voltage_v": 5.0,
                "output_net": "mid",
                "output_min_v": 2.4,
                "output_max_v": 2.6
            }]
        }
        res = self.run_engine(payload)
        self.assertEqual(res["status"], "PASS")

    def test_i2c_bus_with_pullups(self):
        payload = {
            "schema_version": 1,
            "components": [
                {"id": "MCU1", "type": "arduino", "pins": {"SDA": "sda", "SCL": "scl", "GND": "gnd", "5V": "vcc"}},
                {"id": "SENS", "type": "sensor", "pins": {"SDA": "sda", "SCL": "scl", "GND": "gnd", "VIN": "vcc"}},
                {"id": "R1", "type": "resistor", "value_ohms": 4700, "pins": {"1": "vcc", "2": "sda"}},
                {"id": "R2", "type": "resistor", "value_ohms": 4700, "pins": {"1": "vcc", "2": "scl"}}
            ],
            "wires": [],
            "requirements": [{
                "kind": "i2c",
                "sda_net": "sda",
                "scl_net": "scl",
                "supply_net": "vcc",
                "pullup_resistors": ["R1", "R2"]
            }]
        }
        res = self.run_engine(payload)
        self.assertEqual(res["status"], "PASS")

    def test_motor_with_transistor_and_flyback(self):
        payload = {
            "schema_version": 1,
            "components": [
                {"id": "MCU1", "type": "arduino", "pins": {"9": "ctrl", "GND": "gnd", "5V": "vcc"}},
                {"id": "M1", "type": "motor", "pins": {"1": "vcc", "2": "drain"}},
                {"id": "Q1", "type": "mosfet", "pins": {"gate": "gate_net", "drain": "drain", "source": "gnd"}},
                {"id": "D1", "type": "diode", "pins": {"anode": "drain", "cathode": "vcc"}},
                {"id": "R1", "type": "resistor", "value_ohms": 1000, "pins": {"1": "ctrl", "2": "gate_net"}}
            ],
            "wires": [],
            "requirements": [{"kind": "inductive_load", "component_id": "M1"}]
        }
        res = self.run_engine(payload)
        self.assertNotIn("INDUCTIVE_LOAD_NO_FLYBACK", [f["code"] for f in res["findings"]])
        self.assertNotIn("FLYBACK_DIODE_REVERSED", [f["code"] for f in res["findings"]])

    def test_regulator_circuit(self):
        payload = {
            "schema_version": 1,
            "components": [
                {"id": "V1", "type": "supply", "pins": {"positive": "vin", "negative": "gnd"}},
                {"id": "U1", "type": "regulator", "pins": {"IN": "vin", "OUT": "vout", "GND": "gnd"}}
            ],
            "wires": [],
            "requirements": [{
                "kind": "regulator",
                "component_id": "U1",
                "input_voltage_v": 9.0,
                "output_voltage_v": 5.0,
                "dropout_v": 2.0,
                "max_input_voltage_v": 35.0
            }]
        }
        res = self.run_engine(payload)
        self.assertEqual(res["status"], "PASS")

    def test_simple_resistor_network(self):
        payload = {
            "schema_version": 1,
            "components": [
                {"id": "V1", "type": "supply", "pins": {"positive": "vcc", "negative": "gnd"}},
                {"id": "R1", "type": "resistor", "value_ohms": 1000, "pins": {"1": "vcc", "2": "mid"}},
                {"id": "R2", "type": "resistor", "value_ohms": 1000, "pins": {"1": "mid", "2": "gnd"}}
            ],
            "wires": [],
            "requirements": [{
                "kind": "dc_operating_point",
                "ground_net": "gnd",
                "expected_node_ranges": {"mid": [2.4, 2.6]}
            }]
        }
        # DC solver requires voltage in supply
        payload["components"][0]["voltage_v"] = 5.0
        res = self.run_engine(payload)
        self.assertEqual(res["status"], "PASS")

    # Faulty Circuits
    def test_led_without_resistor(self):
        payload = {
            "schema_version": 1,
            "components": [
                {"id": "MCU1", "type": "arduino", "pins": {"13": "net1", "GND": "gnd", "5V": "vcc"}},
                {"id": "D1", "type": "led", "pins": {"anode": "net1", "cathode": "gnd"}}
            ],
            "wires": [{"from": "vcc", "to": "net1"}],
            "requirements": []
        }
        res = self.run_engine(payload)
        self.assertIn("LED_CURRENT_LIMITER_MISSING", [f["code"] for f in res["findings"]])

    def test_led_backwards(self):
        payload = {
            "schema_version": 1,
            "components": [
                {"id": "MCU1", "type": "arduino", "pins": {"13": "net1", "GND": "gnd", "5V": "vcc"}},
                {"id": "D1", "type": "led", "pins": {"anode": "gnd", "cathode": "net2"}},
                {"id": "R1", "type": "resistor", "value_ohms": 220, "pins": {"1": "net1", "2": "net2"}}
            ],
            "wires": [{"from": "vcc", "to": "net1"}],
            "requirements": []
        }
        res = self.run_engine(payload)
        self.assertIn("LED_REVERSED_POLARITY", [f["code"] for f in res["findings"]])

    def test_led_with_too_small_resistor(self):
        payload = {
            "schema_version": 1,
            "components": [
                {"id": "MCU1", "type": "arduino", "pins": {"13": "net1", "GND": "gnd", "5V": "vcc"}},
                {"id": "D1", "type": "led", "pins": {"anode": "net2", "cathode": "gnd"}},
                {"id": "R1", "type": "resistor", "value_ohms": 10, "pins": {"1": "net1", "2": "net2"}}
            ],
            "wires": [{"from": "vcc", "to": "net1"}],
            "requirements": []
        }
        res = self.run_engine(payload)
        self.assertIn("LED_CURRENT_LIMITER_TOO_LOW", [f["code"] for f in res["findings"]])

    def test_button_without_pullup(self):
        payload = {
            "schema_version": 1,
            "components": [
                {"id": "MCU1", "type": "arduino", "pins": {"2": "button_net", "GND": "gnd", "5V": "vcc"}},
                {"id": "SW1", "type": "button", "pins": {"1": "button_net", "2": "gnd"}}
            ],
            "wires": [],
            "requirements": []
        }
        res = self.run_engine(payload)
        self.assertIn("FLOATING_INPUT", [f["code"] for f in res["findings"]])

    def test_motor_directly_on_gpio(self):
        payload = {
            "schema_version": 1,
            "components": [
                {"id": "MCU1", "type": "arduino", "pins": {"9": "ctrl", "GND": "gnd", "5V": "vcc"}},
                {"id": "M1", "type": "motor", "pins": {"1": "ctrl", "2": "gnd"}}
            ],
            "wires": [],
            "requirements": []
        }
        res = self.run_engine(payload)
        self.assertIn("MOTOR_DIRECT_GPIO", [f["code"] for f in res["findings"]])

    def test_motor_without_flyback(self):
        payload = {
            "schema_version": 1,
            "components": [
                {"id": "MCU1", "type": "arduino", "pins": {"9": "ctrl", "GND": "gnd", "5V": "vcc"}},
                {"id": "M1", "type": "motor", "pins": {"1": "vcc", "2": "drain"}},
                {"id": "Q1", "type": "mosfet", "pins": {"gate": "ctrl", "drain": "drain", "source": "gnd"}},
            ],
            "wires": [],
            "requirements": [{"kind": "inductive_load", "component_id": "M1"}]
        }
        res = self.run_engine(payload)
        codes = [f["code"] for f in res["findings"]]
        self.assertIn("INDUCTIVE_LOAD_NO_FLYBACK", codes)

    def test_reversed_electrolytic_capacitor(self):
        payload = {
            "schema_version": 1,
            "components": [
                {"id": "V1", "type": "supply", "pins": {"positive": "vcc", "negative": "gnd"}},
                {"id": "C1", "type": "electrolytic_capacitor", "pins": {"positive": "gnd", "negative": "vcc"}}
            ],
            "wires": [],
            "requirements": []
        }
        res = self.run_engine(payload)
        self.assertIn("CAPACITOR_REVERSED_POLARITY", [f["code"] for f in res["findings"]])

    def test_component_self_short(self):
        payload = {
            "schema_version": 1,
            "components": [
                {"id": "R1", "type": "resistor", "value_ohms": 1000, "pins": {"1": "net1", "2": "net1"}},
                {"id": "V1", "type": "supply", "pins": {"positive": "vcc", "negative": "gnd"}}
            ],
            "wires": [],
            "requirements": []
        }
        res = self.run_engine(payload)
        self.assertIn("COMPONENT_SELF_SHORT", [f["code"] for f in res["findings"]])

    def test_power_short(self):
        payload = {
            "schema_version": 1,
            "components": [
                {"id": "V1", "type": "supply", "pins": {"positive": "vcc", "negative": "gnd"}}
            ],
            "wires": [{"from": "vcc", "to": "gnd"}],
            "requirements": []
        }
        res = self.run_engine(payload)
        self.assertIn("DIRECT_POWER_SHORT", [f["code"] for f in res["findings"]])

    def test_inter_rail_short(self):
        payload = {
            "schema_version": 1,
            "components": [
                {"id": "V1", "type": "supply", "pins": {"positive": "5v", "negative": "gnd"}},
                {"id": "V2", "type": "supply", "pins": {"positive": "3v3", "negative": "gnd"}}
            ],
            "wires": [{"from": "5v", "to": "3v3"}],
            "requirements": []
        }
        res = self.run_engine(payload)
        self.assertIn("INTER_RAIL_SHORT", [f["code"] for f in res["findings"]])

    def test_voltage_divider_wrong_ratio(self):
        payload = {
            "schema_version": 1,
            "components": [
                {"id": "R1", "type": "resistor", "value_ohms": 10000, "pins": {"1": "vcc", "2": "mid"}},
                {"id": "R2", "type": "resistor", "value_ohms": 1000, "pins": {"1": "mid", "2": "gnd"}}
            ],
            "wires": [],
            "requirements": [{
                "kind": "voltage_divider",
                "upper_resistor": "R1",
                "lower_resistor": "R2",
                "input_voltage_v": 5.0,
                "output_net": "mid",
                "output_min_v": 2.4,
                "output_max_v": 2.6
            }]
        }
        res = self.run_engine(payload)
        self.assertIn("DIVIDER_OUTPUT_OUT_OF_RANGE", [f["code"] for f in res["findings"]])

    def test_i2c_missing_pullups(self):
        payload = {
            "schema_version": 1,
            "components": [
                {"id": "MCU1", "type": "arduino", "pins": {"SDA": "sda", "SCL": "scl", "GND": "gnd", "5V": "vcc"}},
                {"id": "SENS", "type": "sensor", "pins": {"SDA": "sda", "SCL": "scl", "GND": "gnd", "VIN": "vcc"}}
            ],
            "wires": [],
            "requirements": [{
                "kind": "i2c",
                "sda_net": "sda",
                "scl_net": "scl",
                "supply_net": "vcc"
            }]
        }
        res = self.run_engine(payload)
        self.assertIn("I2C_PULLUPS_MISSING", [f["code"] for f in res["findings"]])

    def test_regulator_dropout(self):
        payload = {
            "schema_version": 1,
            "components": [
                {"id": "U1", "type": "regulator", "pins": {"IN": "vin", "OUT": "vout", "GND": "gnd"}}
            ],
            "wires": [],
            "requirements": [{
                "kind": "regulator",
                "component_id": "U1",
                "input_voltage_v": 6.0,
                "output_voltage_v": 5.0,
                "dropout_v": 2.0,
                "max_input_voltage_v": 35.0
            }]
        }
        res = self.run_engine(payload)
        self.assertIn("REGULATOR_DROPOUT", [f["code"] for f in res["findings"]])

    def test_gpio_overcurrent(self):
        payload = {
            "schema_version": 1,
            "components": [{"id": "MCU1", "type": "arduino", "pins": {"5V": "vcc", "GND": "gnd"}}],
            "wires": [],
            "requirements": [{
                "kind": "gpio_output",
                "load_current_ma": 50,
                "max_current_ma": 20
            }]
        }
        res = self.run_engine(payload)
        self.assertIn("GPIO_CURRENT_LIMIT_EXCEEDED", [f["code"] for f in res["findings"]])

    def test_resistor_power_exceeded(self):
        payload = {
            "schema_version": 1,
            "components": [
                {
                    "id": "R1", 
                    "type": "resistor", 
                    "value_ohms": 10, 
                    "voltage_across_v": 5.0, 
                    "power_rating_w": 0.25,
                    "pins": {"1": "net1", "2": "net2"}
                }
            ],
            "wires": [],
            "requirements": []
        }
        res = self.run_engine(payload)
        self.assertIn("RESISTOR_POWER_EXCEEDED", [f["code"] for f in res["findings"]])

    def test_logic_level_overvoltage(self):
        payload = {
            "schema_version": 1,
            "components": [{"id": "MCU1", "type": "arduino", "pins": {"5V": "vcc", "GND": "gnd"}}],
            "wires": [],
            "requirements": [{
                "kind": "logic_level_interface",
                "source_high_v": 5.0,
                "destination_max_v": 3.6
            }]
        }
        res = self.run_engine(payload)
        self.assertIn("LOGIC_LEVEL_OVERVOLTAGE", [f["code"] for f in res["findings"]])

    # Edge Cases
    def test_empty_components_list(self):
        payload = {
            "schema_version": 1,
            "components": [],
            "wires": [],
            "requirements": []
        }
        with self.assertRaises(CircuitIRError):
            self.run_engine(payload)

    def test_only_mcu(self):
        payload = {
            "schema_version": 1,
            "components": [{"id": "MCU1", "type": "arduino", "pins": {"5V": "vcc", "GND": "gnd"}}],
            "wires": [],
            "requirements": []
        }
        res = self.run_engine(payload)
        self.assertEqual(res["status"], "PASS")

    def test_multiple_faults(self):
        payload = {
            "schema_version": 1,
            "components": [
                {"id": "MCU1", "type": "arduino", "pins": {"13": "net1", "GND": "gnd", "5V": "vcc"}},
                {"id": "D1", "type": "led", "pins": {"anode": "net1", "cathode": "gnd"}}
            ],
            "wires": [{"from": "vcc", "to": "gnd"}, {"from": "vcc", "to": "net1"}],
            "requirements": []
        }
        res = self.run_engine(payload)
        codes = [f["code"] for f in res["findings"]]
        self.assertIn("DIRECT_POWER_SHORT", codes)
        self.assertIn("LED_CURRENT_LIMITER_MISSING", codes)

    def test_led_with_cathode_resistor(self):
        payload = {
            "schema_version": 1,
            "components": [
                {"id": "MCU1", "type": "arduino", "pins": {"13": "net1", "GND": "gnd", "5V": "vcc"}},
                {"id": "D1", "type": "led", "pins": {"anode": "net1", "cathode": "net2"}},
                {"id": "R1", "type": "resistor", "value_ohms": 220, "pins": {"1": "net2", "2": "gnd"}}
            ],
            "wires": [{"from": "vcc", "to": "net1"}],
            "requirements": []
        }
        res = self.run_engine(payload)
        self.assertNotIn("LED_CURRENT_LIMITER_MISSING", [f["code"] for f in res["findings"]])

    def test_capacitor_at_dc(self):
        payload = {
            "schema_version": 1,
            "components": [
                {"id": "V1", "type": "supply", "voltage_v": 5.0, "pins": {"positive": "vcc", "negative": "gnd"}},
                {"id": "R1", "type": "resistor", "value_ohms": 1000, "pins": {"1": "vcc", "2": "mid"}},
                {"id": "C1", "type": "capacitor", "pins": {"1": "mid", "2": "gnd"}}
            ],
            "wires": [],
            "requirements": [{
                "kind": "dc_operating_point",
                "ground_net": "gnd",
                "expected_node_ranges": {"mid": [4.9, 5.1]}
            }]
        }
        res = self.run_engine(payload)
        self.assertEqual(res["status"], "PASS")

    def test_large_circuit(self):
        components = [{"id": f"R{i}", "type": "resistor", "value_ohms": 1000, "pins": {"1": f"net{i}", "2": f"net{i+1}"}} for i in range(15)]
        components.append({"id": "V1", "type": "supply", "pins": {"positive": "net0", "negative": "net15"}})
        payload = {
            "schema_version": 1,
            "components": components,
            "wires": [],
            "requirements": []
        }
        res = self.run_engine(payload)
        self.assertEqual(res["status"], "PASS")

if __name__ == '__main__':
    unittest.main()
