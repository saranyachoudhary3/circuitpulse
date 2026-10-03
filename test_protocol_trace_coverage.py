import unittest
from logic.protocol_trace import ProtocolTraceEvaluator, ProtocolTraceError
from unittest.mock import MagicMock

class TestProtocolTraceCoverage(unittest.TestCase):
    def setUp(self):
        self.evaluator = ProtocolTraceEvaluator()
        
    def create_circuit(self, digital_trace):
        circuit = MagicMock()
        circuit.measurements = {"digital_trace": digital_trace}
        circuit.canonical_net = lambda x: x
        return circuit

    def test_i2c_valid_transaction(self):
        trace = [
            {"time_us": 10.0, "levels": {"SCL": 1, "SDA": 1}},
            {"time_us": 20.0, "levels": {"SCL": 1, "SDA": 0}}, # START
            {"time_us": 30.0, "levels": {"SCL": 0, "SDA": 0}},
            # byte: 0x40 (0100 0000)
            {"time_us": 40.0, "levels": {"SCL": 1, "SDA": 0}}, # bit 7
            {"time_us": 50.0, "levels": {"SCL": 0, "SDA": 0}},
            {"time_us": 55.0, "levels": {"SCL": 0, "SDA": 1}},
            {"time_us": 60.0, "levels": {"SCL": 1, "SDA": 1}}, # bit 6
            {"time_us": 70.0, "levels": {"SCL": 0, "SDA": 1}},
            {"time_us": 75.0, "levels": {"SCL": 0, "SDA": 0}},
            {"time_us": 80.0, "levels": {"SCL": 1, "SDA": 0}}, # bit 5
            {"time_us": 90.0, "levels": {"SCL": 0, "SDA": 0}},
            {"time_us": 100.0, "levels": {"SCL": 1, "SDA": 0}}, # bit 4
            {"time_us": 110.0, "levels": {"SCL": 0, "SDA": 0}},
            {"time_us": 120.0, "levels": {"SCL": 1, "SDA": 0}}, # bit 3
            {"time_us": 130.0, "levels": {"SCL": 0, "SDA": 0}},
            {"time_us": 140.0, "levels": {"SCL": 1, "SDA": 0}}, # bit 2
            {"time_us": 150.0, "levels": {"SCL": 0, "SDA": 0}},
            {"time_us": 160.0, "levels": {"SCL": 1, "SDA": 0}}, # bit 1
            {"time_us": 170.0, "levels": {"SCL": 0, "SDA": 0}},
            {"time_us": 180.0, "levels": {"SCL": 1, "SDA": 0}}, # bit 0
            {"time_us": 190.0, "levels": {"SCL": 0, "SDA": 0}},
            {"time_us": 200.0, "levels": {"SCL": 1, "SDA": 0}}, # ACK bit (0)
            {"time_us": 210.0, "levels": {"SCL": 0, "SDA": 0}},
            {"time_us": 220.0, "levels": {"SCL": 1, "SDA": 0}}, # before STOP
            {"time_us": 225.0, "levels": {"SCL": 1, "SDA": 1}}, # STOP
        ]
        circuit = self.create_circuit(trace)
        rule = {"kind": "i2c_trace", "scl_net": "SCL", "sda_net": "SDA", "expected_addresses": ["0x20"]}
        res = self.evaluator.evaluate(circuit, rule)
        self.assertEqual(res["status"], "PASS")

    def test_i2c_nack(self):
        trace = [
            {"time_us": 10.0, "levels": {"SCL": 1, "SDA": 1}},
            {"time_us": 20.0, "levels": {"SCL": 1, "SDA": 0}}, # START
            {"time_us": 30.0, "levels": {"SCL": 0, "SDA": 0}},
            # byte: 0x40 (0100 0000)
            {"time_us": 40.0, "levels": {"SCL": 1, "SDA": 0}}, # bit 7
            {"time_us": 50.0, "levels": {"SCL": 0, "SDA": 0}},
            {"time_us": 55.0, "levels": {"SCL": 0, "SDA": 1}},
            {"time_us": 60.0, "levels": {"SCL": 1, "SDA": 1}}, # bit 6
            {"time_us": 70.0, "levels": {"SCL": 0, "SDA": 1}},
            {"time_us": 75.0, "levels": {"SCL": 0, "SDA": 0}},
            {"time_us": 80.0, "levels": {"SCL": 1, "SDA": 0}}, # bit 5
            {"time_us": 90.0, "levels": {"SCL": 0, "SDA": 0}},
            {"time_us": 100.0, "levels": {"SCL": 1, "SDA": 0}}, # bit 4
            {"time_us": 110.0, "levels": {"SCL": 0, "SDA": 0}},
            {"time_us": 120.0, "levels": {"SCL": 1, "SDA": 0}}, # bit 3
            {"time_us": 130.0, "levels": {"SCL": 0, "SDA": 0}},
            {"time_us": 140.0, "levels": {"SCL": 1, "SDA": 0}}, # bit 2
            {"time_us": 150.0, "levels": {"SCL": 0, "SDA": 0}},
            {"time_us": 160.0, "levels": {"SCL": 1, "SDA": 0}}, # bit 1
            {"time_us": 170.0, "levels": {"SCL": 0, "SDA": 0}},
            {"time_us": 180.0, "levels": {"SCL": 1, "SDA": 0}}, # bit 0
            {"time_us": 190.0, "levels": {"SCL": 0, "SDA": 0}},
            {"time_us": 195.0, "levels": {"SCL": 0, "SDA": 1}},
            {"time_us": 200.0, "levels": {"SCL": 1, "SDA": 1}}, # NACK bit (1)
            {"time_us": 210.0, "levels": {"SCL": 0, "SDA": 1}},
            {"time_us": 215.0, "levels": {"SCL": 0, "SDA": 0}},
            {"time_us": 220.0, "levels": {"SCL": 1, "SDA": 0}}, # before STOP
            {"time_us": 225.0, "levels": {"SCL": 1, "SDA": 1}}, # STOP
        ]
        circuit = self.create_circuit(trace)
        rule = {"kind": "i2c_trace", "scl_net": "SCL", "sda_net": "SDA"}
        res = self.evaluator.evaluate(circuit, rule)
        self.assertEqual(res["status"], "FAIL")
        self.assertTrue(any("I2C_NACK" in w["code"] for w in res["findings"]))

    def test_spi_timing(self):
        trace = [
            {"time_us": 0.0, "levels": {"CS": 1, "SCK": 0, "MOSI": 0, "MISO": 0}},
            {"time_us": 10.0, "levels": {"CS": 0, "SCK": 0, "MOSI": 0, "MISO": 0}}, # CS active
            {"time_us": 20.0, "levels": {"CS": 0, "SCK": 1, "MOSI": 1, "MISO": 0}}, # SCK rise (sample point)
            {"time_us": 25.0, "levels": {"CS": 0, "SCK": 0, "MOSI": 1, "MISO": 0}}, # SCK fall
            {"time_us": 30.0, "levels": {"CS": 0, "SCK": 1, "MOSI": 0, "MISO": 1}}, # SCK rise (sample point) -> period = 10us
        ]
        circuit = self.create_circuit(trace)
        rule = {"kind": "spi_trace", "cs_net": "CS", "sck_net": "SCK", "mosi_net": "MOSI", "miso_net": "MISO", "min_clock_period_us": 15.0}
        res = self.evaluator.evaluate(circuit, rule)
        self.assertEqual(res["status"], "FAIL")
        self.assertTrue(any("SPI_CLOCK_TOO_FAST" in w["code"] for w in res["findings"]))

    def test_uart_baud_rate(self):
        trace = [
            {"time_us": 0.0, "levels": {"RX": 1}},
            {"time_us": 100.0, "levels": {"RX": 0}}, # START bit
            {"time_us": 200.0, "levels": {"RX": 1}}, # bit 0
            {"time_us": 300.0, "levels": {"RX": 0}}, # bit 1
            {"time_us": 400.0, "levels": {"RX": 1}}, # bit 2
            {"time_us": 500.0, "levels": {"RX": 0}}, # bit 3
            {"time_us": 600.0, "levels": {"RX": 1}}, # bit 4
            {"time_us": 700.0, "levels": {"RX": 0}}, # bit 5
            {"time_us": 800.0, "levels": {"RX": 1}}, # bit 6
            {"time_us": 900.0, "levels": {"RX": 0}}, # bit 7
            {"time_us": 1000.0, "levels": {"RX": 1}}, # STOP bit
        ]
        circuit = self.create_circuit(trace)
        rule = {"kind": "uart_trace", "rx_net": "RX", "baud": 10000}
        res = self.evaluator.evaluate(circuit, rule)
        self.assertEqual(res["status"], "PASS")

    def test_invalid_trace_handling(self):
        circuit = self.create_circuit([])
        rule = {"kind": "uart_trace", "rx_net": "RX", "baud": 9600}
        with self.assertRaises(ProtocolTraceError):
            self.evaluator.evaluate(circuit, rule)
            
        circuit = self.create_circuit([{"time_us": "not_a_number", "levels": {}}])
        with self.assertRaises(ProtocolTraceError):
            self.evaluator.evaluate(circuit, rule)
