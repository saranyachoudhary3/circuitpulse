import unittest
from logic.circuit_ir import CircuitIR, _UnionFind, CircuitIRError

class TestCircuitIRv2(unittest.TestCase):
    def test_union_find_power_priority(self):
        uf = _UnionFind()
        uf.union("net1", "GND")
        self.assertEqual(uf.find("net1"), "GND")
        
        uf2 = _UnionFind()
        uf2.union("GND", "net1")
        self.assertEqual(uf2.find("net1"), "GND")
        
        uf3 = _UnionFind()
        uf3.union("net2", "VCC")
        self.assertEqual(uf3.find("net2"), "VCC")

    def test_self_loop_filtered(self):
        payload = {
            "components": [
                {"id": "R1", "type": "resistor", "pins": {"1": "net1", "2": "net2"}}
            ],
            "wires": [
                {"from": "net1", "to": "net1"},
                {"from": "net1", "to": "net2"}
            ]
        }
        circuit = CircuitIR(payload)
        self.assertEqual(circuit.canonical_net("net1"), circuit.canonical_net("net2"))

    def test_power_nets_list(self):
        uf = _UnionFind()
        uf.union("net1", "5V")
        self.assertEqual(uf.find("net1"), "5V")
        uf.union("3V3", "net2")
        self.assertEqual(uf.find("net2"), "3V3")
        
    def test_non_power_backward_compatible(self):
        uf = _UnionFind()
        uf.union("netA", "netB")
        self.assertEqual(uf.find("netA"), "netA")
        self.assertEqual(uf.find("netB"), "netA")

if __name__ == '__main__':
    unittest.main()
