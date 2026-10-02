import unittest

from logic.logic_engine import CircuitLogicEngine


def i2c_trace(byte=0x76, ack=0):
    events = [{"time_us": 0, "levels": {"SDA": 1, "SCL": 1}}, {"time_us": 1, "levels": {"SDA": 0}}]
    moment = 2
    for bit in [int(item) for item in f"{byte:08b}"] + [ack]:
        events.extend([{"time_us": moment, "levels": {"SCL": 0, "SDA": bit}}, {"time_us": moment + 1, "levels": {"SCL": 1}}])
        moment += 2
    events.extend([{"time_us": moment, "levels": {"SCL": 0, "SDA": 0}}, {"time_us": moment + 1, "levels": {"SCL": 1}}, {"time_us": moment + 2, "levels": {"SDA": 1}}])
    return events


class ProtocolTraceTests(unittest.TestCase):
    def setUp(self):
        self.engine = CircuitLogicEngine()

    def test_i2c_trace_decodes_address_and_ack(self):
        circuit = {"components": [{"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}}],
                   "measurements": {"digital_trace": i2c_trace(0xEC)},
                   "requirements": [{"kind": "i2c_trace", "sda_net": "SDA", "scl_net": "SCL", "expected_addresses": [0x76]}]}
        self.assertEqual(self.engine.analyze(circuit)["status"], "PASS")

    def test_i2c_nack_is_an_electrical_fault(self):
        circuit = {"components": [{"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}}],
                   "measurements": {"digital_trace": i2c_trace(0xEC, ack=1)},
                   "requirements": [{"kind": "i2c_trace", "sda_net": "SDA", "scl_net": "SCL"}]}
        result = self.engine.analyze(circuit)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("I2C_NACK", {item["code"] for item in result["findings"]})

    def test_i2c_payload_byte_cannot_satisfy_expected_address(self):
        # The first decoded byte is address 0x20; a later payload can happen
        # to look like 0x76<<1 but must not satisfy expected_addresses.
        trace = i2c_trace(0x40)
        circuit = {"components": [{"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}}],
                   "measurements": {"digital_trace": trace},
                   "requirements": [{"kind": "i2c_trace", "sda_net": "SDA", "scl_net": "SCL", "expected_addresses": [0x76]}]}
        result = self.engine.analyze(circuit)
        self.assertIn("I2C_EXPECTED_ADDRESS_MISSING", {item["code"] for item in result["findings"]})

    def test_uart_payload_is_checked_against_waveform(self):
        # 1 Mbps, one 0x55 frame: idle, start, alternating data bits, stop.
        trace = [{"time_us": 0, "levels": {"RX": 1}}, {"time_us": 1, "levels": {"RX": 0}}]
        for index, value in enumerate([1, 0, 1, 0, 1, 0, 1, 0, 1]):
            trace.append({"time_us": 2 + index, "levels": {"RX": value}})
        circuit = {"components": [{"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}}],
                   "measurements": {"digital_trace": trace},
                   "requirements": [{"kind": "uart_trace", "rx_net": "RX", "baud": 1000000, "expected_bytes": [0x55]}]}
        self.assertEqual(self.engine.analyze(circuit)["status"], "PASS")
