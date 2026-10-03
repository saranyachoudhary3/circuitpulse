import unittest

from logic.repair_planner import RepairPlanner


class TestRepairGuidance(unittest.TestCase):
    def setUp(self):
        self.planner = RepairPlanner()

    def test_no_faults(self):
        preset = {"connections": [{"id": "C1", "from": "A", "to": "B"}], "build_order": [{"id": "C1"}]}
        observed = [{"from": "A", "to": "B"}]
        res = self.planner.plan(preset, observed)
        self.assertEqual(len(res["actions"]), 0)
        self.assertEqual(len(res["tutorial_steps"]), 0)

    def test_one_missing_wire(self):
        preset = {"connections": [{"id": "C1", "from": "A", "to": "B"}]}
        observed = []
        res = self.planner.plan(preset, observed)
        self.assertEqual(len(res["actions"]), 1)
        self.assertEqual(res["actions"][0]["kind"], "add")
        self.assertIn("Connect a wire from", res["tutorial_steps"][0]["instruction"])
        self.assertEqual(res["tutorial_steps"][-1]["instruction"], "Reconnect power and verify the circuit")

    def test_one_extra_wire(self):
        preset = {"connections": []}
        observed = [{"from": "A", "to": "B"}]
        res = self.planner.plan(preset, observed)
        self.assertEqual(len(res["actions"]), 1)
        self.assertEqual(res["actions"][0]["kind"], "remove")
        self.assertIn("Remove the wire", res["tutorial_steps"][0]["instruction"])

    def test_power_short(self):
        preset = {"connections": []}
        observed = [{"from": "MCU_5V", "to": "MCU_GND"}]
        res = self.planner.plan(preset, observed)
        actions = res["actions"]
        self.assertEqual(actions[0]["kind"], "safety")
        self.assertEqual(actions[1]["kind"], "remove")
        self.assertEqual(actions[1]["priority"], 0)
        self.assertIn("Disconnect", res["tutorial_steps"][0]["instruction"])

    def test_multiple_missing_wires_ordered(self):
        preset = {
            "connections": [
                {"id": "W1", "from": "A", "to": "B"},
                {"id": "W2", "from": "C", "to": "D"}
            ],
            "build_order": [{"id": "W2"}, {"id": "W1"}]
        }
        observed = []
        res = self.planner.plan(preset, observed)
        actions = res["actions"]
        self.assertEqual(len(actions), 2)
        # Priority: 10 + build_order index.
        # W2 gets index 0 -> pri 10
        # W1 gets index 1 -> pri 11
        # Smaller priority first
        self.assertIn("C <-> D", actions[0]["connection_id"])
        self.assertIn("A <-> B", actions[1]["connection_id"])

    def test_wire_move(self):
        preset = {"connections": [{"id": "C1", "from": "A", "to": "B"}]}
        observed = [{"from": "A", "to": "C"}]
        res = self.planner.plan(preset, observed)
        actions = res["actions"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["kind"], "move")
        self.assertEqual(actions[0]["old_end"], "C")
        self.assertEqual(actions[0]["new_end"], "B")
        self.assertEqual(actions[0]["fixed"], "A")

    def test_mix_priority_ordering(self):
        preset = {"connections": [{"id": "C1", "from": "A", "to": "B"}]}
        observed = [{"from": "C", "to": "D"}]
        findings = [{"code": "ERR1", "severity": "error", "message": "msg1"}]
        res = self.planner.plan(preset, observed, findings)
        actions = res["actions"]
        # priorities:
        # C<->D remove: 1 (not power short)
        # finding: 2
        # add A<->B: 10+
        self.assertEqual(len(actions), 3)
        self.assertEqual(actions[0]["kind"], "remove")
        self.assertEqual(actions[1]["kind"], "electrical_repair")
        self.assertEqual(actions[2]["kind"], "add")

    def test_tutorial_steps_numbered(self):
        preset = {"connections": [{"id": "C1", "from": "A", "to": "B"}]}
        observed = [{"from": "C", "to": "D"}]
        res = self.planner.plan(preset, observed)
        steps = res["tutorial_steps"]
        # step 1: remove, step 2: add, step 3: reconnect
        self.assertEqual(steps[0]["step"], 1)
        self.assertEqual(steps[1]["step"], 2)
        self.assertEqual(steps[2]["step"], 3)

    def test_tutorial_ends_with_reconnect(self):
        preset = {"connections": [{"id": "C1", "from": "A", "to": "B"}]}
        observed = []
        res = self.planner.plan(preset, observed)
        self.assertEqual(res["tutorial_steps"][-1]["instruction"], "Reconnect power and verify the circuit")

    def test_electrical_repair_uses_finding_message(self):
        preset = {"connections": []}
        observed = []
        findings = [{"code": "F1", "severity": "error", "message": "My message", "recommended_action": ""}]
        res = self.planner.plan(preset, observed, findings)
        self.assertEqual(res["actions"][0]["instruction"], "My message")
        
        findings2 = [{"code": "F2", "severity": "error", "message": "Msg", "recommended_action": "Do this"}]
        res2 = self.planner.plan(preset, observed, findings2)
        self.assertEqual(res2["actions"][0]["instruction"], "Do this")

    def test_all_rail_name_patterns(self):
        rails = [
            (":5v", ":gnd"),
            (":3v3", ":ground"),
            (":vin", ":agnd"),
            (":vbus", ":gnd_d"),
            (":12v", ":vss"),
            (":9v", ":com"),
            (":vcc", ":gnd"),
            (":vdd", ":gnd"),
        ]
        preset = {"connections": []}
        for pos, neg in rails:
            observed = [{"from": pos, "to": neg}]
            res = self.planner.plan(preset, observed)
            self.assertEqual(res["actions"][0]["kind"], "safety")

    def test_safety_precondition(self):
        preset = {"connections": []}
        observed = [{"from": "MCU_5V", "to": "MCU_GND"}]
        res = self.planner.plan(preset, observed)
        self.assertEqual(res["tutorial_steps"][0]["safety_note"], "CRITICAL: Do this before touching any wires.")

    def test_complex_scenario(self):
        preset = {
            "connections": [
                {"id": "W1", "from": "A", "to": "B"},
                {"id": "W2", "from": "C", "to": "D"},
                {"id": "W3", "from": "E", "to": "F"}
            ]
        }
        observed = [
            {"from": "MCU_5V", "to": "MCU_GND"},
            {"from": "G", "to": "H"}
        ]
        res = self.planner.plan(preset, observed)
        actions = res["actions"]
        # safety -> remove short (pri 0) -> remove GH (pri 1) -> add 3 wires
        self.assertEqual(actions[0]["kind"], "safety")
        self.assertEqual(actions[1]["kind"], "remove")
        self.assertEqual(actions[1]["priority"], 0)
        self.assertEqual(actions[2]["kind"], "remove")
        self.assertEqual(actions[2]["priority"], 1)
        self.assertEqual(actions[3]["kind"], "add")
        self.assertEqual(actions[4]["kind"], "add")
        self.assertEqual(actions[5]["kind"], "add")

    def test_empty_preset(self):
        preset = {}
        observed = [{"from": "A", "to": "B"}]
        res = self.planner.plan(preset, observed)
        self.assertEqual(res["actions"][0]["kind"], "remove")

    def test_component_specs_used(self):
        preset = {"connections": [{"id": "C1", "from": "A", "to": "B", "wire_color": "blue"}]}
        observed = []
        res = self.planner.plan(preset, observed)
        self.assertIn("blue wire", res["actions"][0]["instruction"])


if __name__ == '__main__':
    unittest.main()
