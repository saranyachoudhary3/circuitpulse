import unittest
from logic.netlist import NetlistVerifier
from logic.circuit_ir import CircuitIR
from logic.logic_engine import CircuitLogicEngine
from logic.session import GraphSession
from logic.repair_planner import RepairPlanner

class TestCircuitImprovementsV2(unittest.TestCase):

    def test_r1_floating_input_no_pullup(self):
        verifier = NetlistVerifier()
        netlist = {
            "components": [
                {"id": "U1", "type": "mcu", "pins": {"GND": "gnd", "D2": "net_switch"}},
                {"id": "SW1", "type": "button", "pins": {"1": "net_switch", "2": "gnd"}}
            ]
        }
        res = verifier.verify(netlist)
        floating = [f for f in res["findings"] if f["code"] == "FLOATING_INPUT"]
        self.assertEqual(len(floating), 1)

    def test_r1_floating_input_with_pullup(self):
        verifier = NetlistVerifier()
        netlist = {
            "components": [
                {"id": "U1", "type": "mcu", "pins": {"VCC": "vcc", "GND": "gnd", "D2": "net_switch"}},
                {"id": "SW1", "type": "button", "pins": {"1": "net_switch", "2": "gnd"}},
                {"id": "R1", "type": "resistor", "value_ohms": 10000, "pins": {"1": "net_switch", "2": "vcc"}}
            ]
        }
        res = verifier.verify(netlist)
        floating = [f for f in res["findings"] if f["code"] == "FLOATING_INPUT"]
        self.assertEqual(len(floating), 0)

    def test_r1_floating_input_with_pulldown(self):
        verifier = NetlistVerifier()
        netlist = {
            "components": [
                {"id": "U1", "type": "mcu", "pins": {"VCC": "vcc", "GND": "gnd", "D2": "net_switch"}},
                {"id": "SW1", "type": "button", "pins": {"1": "net_switch", "2": "vcc"}},
                {"id": "R1", "type": "resistor", "value_ohms": 10000, "pins": {"1": "net_switch", "2": "gnd"}}
            ]
        }
        res = verifier.verify(netlist)
        floating = [f for f in res["findings"] if f["code"] == "FLOATING_INPUT"]
        self.assertEqual(len(floating), 0)

    def test_r1_unused_pin_no_false_positive(self):
        verifier = NetlistVerifier()
        netlist = {
            "components": [
                {"id": "U1", "type": "mcu", "pins": {"VCC": "vcc", "GND": "gnd", "D2": "unused"}}
            ]
        }
        res = verifier.verify(netlist)
        floating = [f for f in res["findings"] if f["code"] == "FLOATING_INPUT"]
        self.assertEqual(len(floating), 0)

    def test_r1_led_pin_no_false_positive(self):
        verifier = NetlistVerifier()
        netlist = {
            "components": [
                {"id": "U1", "type": "mcu", "pins": {"VCC": "vcc", "GND": "gnd", "D2": "led_anode"}},
                {"id": "LED1", "type": "led", "pins": {"anode": "led_anode", "cathode": "gnd"}},
                {"id": "R1", "type": "resistor", "value_ohms": 330, "pins": {"1": "led_anode", "2": "vcc"}}
            ]
        }
        res = verifier.verify(netlist)
        floating = [f for f in res["findings"] if f["code"] == "FLOATING_INPUT"]
        self.assertEqual(len(floating), 0)

    def test_r2_flyback_correct_orientation(self):
        engine = CircuitLogicEngine()
        payload = {
            "components": [
                {"id": "M1", "type": "motor", "pins": {"+": "vcc", "-": "drain"}},
                {"id": "D1", "type": "diode", "pins": {"cathode": "vcc", "anode": "drain"}}
            ],
            "requirements": [
                {"kind": "inductive_load", "component_id": "M1"}
            ]
        }
        res = engine.analyze(payload)
        flyback_warnings = [f for f in res["findings"] if "FLYBACK" in f["code"]]
        self.assertEqual(len(flyback_warnings), 0)

    def test_r2_flyback_missing(self):
        engine = CircuitLogicEngine()
        payload = {
            "components": [
                {"id": "M1", "type": "motor", "pins": {"+": "vcc", "-": "drain"}}
            ],
            "requirements": [
                {"kind": "inductive_load", "component_id": "M1"}
            ]
        }
        res = engine.analyze(payload)
        missing = [f for f in res["findings"] if f["code"] == "INDUCTIVE_LOAD_NO_FLYBACK"]
        self.assertEqual(len(missing), 1)

    def test_r2_flyback_reversed(self):
        engine = CircuitLogicEngine()
        payload = {
            "components": [
                {"id": "M1", "type": "motor", "pins": {"+": "vcc", "-": "drain"}},
                {"id": "D1", "type": "diode", "pins": {"anode": "vcc", "cathode": "drain"}}
            ],
            "requirements": [
                {"kind": "inductive_load", "component_id": "M1"}
            ]
        }
        res = engine.analyze(payload)
        reversed_err = [f for f in res["findings"] if f["code"] == "FLYBACK_DIODE_REVERSED"]
        self.assertEqual(len(reversed_err), 1)

    def test_r2_flyback_relay_correct(self):
        engine = CircuitLogicEngine()
        payload = {
            "components": [
                {"id": "RY1", "type": "relay", "pins": {"+": "vcc", "-": "drain"}},
                {"id": "D1", "type": "diode", "pins": {"cathode": "vcc", "anode": "drain"}}
            ],
            "requirements": [
                {"kind": "inductive_load", "component_id": "RY1"}
            ]
        }
        res = engine.analyze(payload)
        flyback_warnings = [f for f in res["findings"] if "FLYBACK" in f["code"]]
        self.assertEqual(len(flyback_warnings), 0)

    def test_r2_flyback_fallback_missing(self):
        engine = CircuitLogicEngine()
        payload = {
            "components": [
                {"id": "R1", "type": "resistor", "value_ohms": 100, "pins": {"1": "a", "2": "b"}}
            ],
            "requirements": [
                {"kind": "inductive_load", "component_id": "UNKNOWN", "flyback_protection": False}
            ]
        }
        res = engine.analyze(payload)
        missing = [f for f in res["findings"] if f["code"] == "FLYBACK_PROTECTION_MISSING"]
        self.assertEqual(len(missing), 1)

    def test_r3_voltage_divider_unloaded_backward_compatible(self):
        engine = CircuitLogicEngine()
        payload = {
            "components": [
                {"id": "PSU", "type": "supply", "pins": {"+": "vcc", "-": "gnd"}},
                {"id": "R1", "type": "resistor", "value_ohms": 10000, "pins": {"1": "vcc", "2": "out"}},
                {"id": "R2", "type": "resistor", "value_ohms": 10000, "pins": {"1": "out", "2": "gnd"}}
            ],
            "requirements": [
                {
                    "kind": "voltage_divider", "upper_resistor": "R1", "lower_resistor": "R2",
                    "input_voltage_v": 5.0, "output_net": "out",
                    "output_min_v": 2.4, "output_max_v": 2.6
                }
            ]
        }
        res = engine.analyze(payload)
        self.assertEqual(res["status"], "PASS")

    def test_r3_voltage_divider_high_impedance_load(self):
        engine = CircuitLogicEngine()
        payload = {
            "components": [
                {"id": "PSU", "type": "supply", "pins": {"+": "vcc", "-": "gnd"}},
                {"id": "R1", "type": "resistor", "value_ohms": 10000, "pins": {"1": "vcc", "2": "out"}},
                {"id": "R2", "type": "resistor", "value_ohms": 10000, "pins": {"1": "out", "2": "gnd"}}
            ],
            "requirements": [
                {
                    "kind": "voltage_divider", "upper_resistor": "R1", "lower_resistor": "R2",
                    "input_voltage_v": 5.0, "output_net": "out",
                    "output_min_v": 2.4, "output_max_v": 2.6,
                    "load_resistance_ohms": 1000000
                }
            ]
        }
        res = engine.analyze(payload)
        self.assertEqual(res["status"], "PASS")

    def test_r3_voltage_divider_low_impedance_load(self):
        engine = CircuitLogicEngine()
        payload = {
            "components": [
                {"id": "PSU", "type": "supply", "pins": {"+": "vcc", "-": "gnd"}},
                {"id": "R1", "type": "resistor", "value_ohms": 10000, "pins": {"1": "vcc", "2": "out"}},
                {"id": "R2", "type": "resistor", "value_ohms": 10000, "pins": {"1": "out", "2": "gnd"}}
            ],
            "requirements": [
                {
                    "kind": "voltage_divider", "upper_resistor": "R1", "lower_resistor": "R2",
                    "input_voltage_v": 5.0, "output_net": "out",
                    "output_min_v": 2.4, "output_max_v": 2.6,
                    "load_resistance_ohms": 10000
                }
            ]
        }
        res = engine.analyze(payload)
        sag = [f for f in res["findings"] if f["code"] == "VOLTAGE_DIVIDER_LOADED_SAG"]
        out_of_range = [f for f in res["findings"] if f["code"] == "DIVIDER_OUTPUT_OUT_OF_RANGE"]
        self.assertEqual(len(sag), 1)
        self.assertEqual(len(out_of_range), 1)
        # Loaded V_out approx 1.666V
        self.assertAlmostEqual(sag[0]["evidence"]["loaded_v"], 1.6666, places=3)

    def test_r3_voltage_divider_sag_warning(self):
        engine = CircuitLogicEngine()
        payload = {
            "components": [
                {"id": "PSU", "type": "supply", "pins": {"+": "vcc", "-": "gnd"}},
                {"id": "R1", "type": "resistor", "value_ohms": 10000, "pins": {"1": "vcc", "2": "out"}},
                {"id": "R2", "type": "resistor", "value_ohms": 10000, "pins": {"1": "out", "2": "gnd"}}
            ],
            "requirements": [
                {
                    "kind": "voltage_divider", "upper_resistor": "R1", "lower_resistor": "R2",
                    "input_voltage_v": 5.0, "output_net": "out",
                    "output_min_v": 2.0, "output_max_v": 3.0,
                    "load_resistance_ohms": 10000
                }
            ]
        }
        res = engine.analyze(payload)
        # Loaded is 1.67V, which is outside 2.0-3.0 range, unloaded is 2.5V which is inside.
        sag = [f for f in res["findings"] if f["code"] == "VOLTAGE_DIVIDER_LOADED_SAG"]
        out_of_range = [f for f in res["findings"] if f["code"] == "DIVIDER_OUTPUT_OUT_OF_RANGE"]
        self.assertEqual(len(sag), 1)
        self.assertEqual(len(out_of_range), 1)

    def test_r4_session_overall_confidence_field(self):
        preset = {"id": "1", "name": "Test", "connections": [{"id": "c1", "from": "A", "to": "B"}]}
        session = GraphSession(preset)
        state = session.state()
        self.assertIn("overall_confidence", state)
        self.assertEqual(state["overall_confidence"], 1.0) # No connections observed yet

    def test_r4_session_vision_confidence(self):
        preset = {"id": "1", "name": "Test", "connections": [{"id": "c1", "from": "A", "to": "B"}]}
        session = GraphSession(preset)
        for _ in range(GraphSession.STABLE_REQUIRED):
            session.observe([{"from": "A", "to": "B", "confidence": 0.9}])
        state = session.state()
        self.assertAlmostEqual(state["overall_confidence"], 0.7 + (5/7)*0.2)
        
    def test_r4_session_user_confirmed_confidence(self):
        preset = {"id": "1", "name": "Test", "connections": [{"id": "c1", "from": "A", "to": "B"}]}
        session = GraphSession(preset)
        session.confirm("A", "B", True)
        state = session.state()
        self.assertEqual(state["overall_confidence"], 1.0)

    def test_r4_session_min_confidence(self):
        preset = {"id": "1", "name": "Test", "connections": [{"id": "c1", "from": "A", "to": "B"}, {"id": "c2", "from": "C", "to": "D"}]}
        session = GraphSession(preset)
        session.confirm("A", "B", True)
        for _ in range(GraphSession.STABLE_REQUIRED):
            session.observe([{"from": "C", "to": "D", "confidence": 0.9}, {"from": "A", "to": "B", "confidence": 0.9}])
        state = session.state()
        self.assertAlmostEqual(state["overall_confidence"], 0.7 + (5/7)*0.2)

    def test_r4_session_empty_overall_confidence(self):
        preset = {"id": "1", "name": "Test", "connections": []}
        session = GraphSession(preset)
        state = session.state()
        self.assertEqual(state["overall_confidence"], 1.0)
        
    def test_r5_tutorial_starts_with_disconnect(self):
        planner = RepairPlanner()
        preset = {"connections": []} # Empty preset so the short is an extra connection
        observed = [{"from": "_vcc", "to": "_gnd"}]
        # VCC to GND is a power short, it should generate safety action
        plan = planner.plan(preset, observed)
        steps = plan.get("tutorial_steps", [])
        self.assertTrue(len(steps) > 0)
        self.assertIn("Disconnect", steps[0]["instruction"])
        
    def test_r5_tutorial_missing_wire_connect(self):
        planner = RepairPlanner()
        preset = {"connections": [{"id": "1", "from": "A", "to": "B"}]}
        observed = []
        plan = planner.plan(preset, observed)
        steps = plan.get("tutorial_steps", [])
        self.assertTrue(len(steps) >= 2) # connect + reconnect power
        self.assertIn("Connect a wire from A to B", steps[0]["instruction"])
        
    def test_r5_tutorial_sequential_numbering(self):
        planner = RepairPlanner()
        preset = {"connections": [{"id": "1", "from": "A", "to": "B"}, {"id": "2", "from": "C", "to": "D"}]}
        observed = []
        plan = planner.plan(preset, observed)
        steps = plan.get("tutorial_steps", [])
        for i, step in enumerate(steps):
            self.assertEqual(step["step"], i + 1)
            
    def test_r5_tutorial_empty_if_no_issues(self):
        planner = RepairPlanner()
        preset = {"connections": [{"id": "1", "from": "A", "to": "B"}]}
        observed = [{"from": "A", "to": "B"}]
        plan = planner.plan(preset, observed)
        steps = plan.get("tutorial_steps", [])
        self.assertEqual(len(steps), 0)
        
    def test_r5_tutorial_ends_with_reconnect(self):
        planner = RepairPlanner()
        preset = {"connections": [{"id": "1", "from": "A", "to": "B"}]}
        observed = []
        plan = planner.plan(preset, observed)
        steps = plan.get("tutorial_steps", [])
        self.assertIn("Reconnect power", steps[-1]["instruction"])
        
    def test_r5_tutorial_move_wire(self):
        planner = RepairPlanner()
        preset = {"connections": [{"id": "1", "from": "A", "to": "C"}]}
        observed = [{"from": "A", "to": "B"}]
        plan = planner.plan(preset, observed)
        steps = plan.get("tutorial_steps", [])
        self.assertEqual(len(steps), 2) # 1 move + 1 reconnect
        self.assertIn("Move the wire end from B to C, keeping it connected at A", steps[0]["instruction"])

if __name__ == '__main__':
    unittest.main()
