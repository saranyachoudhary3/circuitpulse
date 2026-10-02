import unittest
from logic.repair_planner import RepairPlanner

class TestRepairV2(unittest.TestCase):
    def setUp(self):
        self.planner = RepairPlanner()

    def test_power_short_12v_gnd(self):
        preset = {"connections": []}
        observed = [{"from": "board:12v", "to": "board:gnd"}]
        res = self.planner.plan(preset, observed)
        actions = res["actions"]
        self.assertEqual(actions[0]["kind"], "safety")
        self.assertEqual(actions[1]["kind"], "remove")
        self.assertEqual(actions[1]["priority"], 0)

    def test_power_short_vin_ground(self):
        res = self.planner.plan({"connections": []}, [{"from": "x:vin", "to": "y:ground"}])
        self.assertEqual(res["actions"][0]["kind"], "safety")
        self.assertEqual(res["actions"][1]["priority"], 0)

    def test_power_short_vbus_agnd(self):
        res = self.planner.plan({"connections": []}, [{"from": "u:vbus", "to": "v:agnd"}])
        self.assertEqual(res["actions"][0]["kind"], "safety")
        self.assertEqual(res["actions"][1]["priority"], 0)

    def test_non_power_wire_removal(self):
        res = self.planner.plan({"connections": []}, [{"from": "a:pin1", "to": "b:pin2"}])
        self.assertEqual(len(res["actions"]), 1)
        self.assertEqual(res["actions"][0]["kind"], "remove")
        self.assertEqual(res["actions"][0]["priority"], 1)

    def test_wire_move_detection(self):
        preset = {"connections": [{"from": "A", "to": "C", "id": "1"}]}
        observed = [{"from": "A", "to": "B"}]
        res = self.planner.plan(preset, observed)
        actions = res["actions"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["kind"], "move")
        self.assertTrue("Move the wire end" in actions[0]["instruction"])

    def test_safety_precondition(self):
        preset = {"connections": []}
        observed = [{"from": "board:12v", "to": "board:gnd"}]
        res = self.planner.plan(preset, observed)
        self.assertEqual(res["actions"][0]["kind"], "safety")
        self.assertEqual(res["actions"][0]["priority"], -1)

    def test_existing_scenarios(self):
        preset = {"connections": [{"from": "a", "to": "b", "id": "1"}]}
        observed = [{"from": "c", "to": "d"}]
        res = self.planner.plan(preset, observed)
        actions = res["actions"]
        self.assertEqual(len(actions), 2)
        kinds = [a["kind"] for a in actions]
        self.assertIn("remove", kinds)
        self.assertIn("add", kinds)

    def test_empty_observed_list(self):
        preset = {"connections": [{"from": "a", "to": "b", "id": "1"}]}
        res = self.planner.plan(preset, [])
        self.assertEqual(len(res["actions"]), 1)
        self.assertEqual(res["actions"][0]["kind"], "add")

    def test_all_connections_present(self):
        preset = {"connections": [{"from": "a", "to": "b", "id": "1"}]}
        observed = [{"from": "a", "to": "b"}]
        res = self.planner.plan(preset, observed)
        self.assertEqual(len(res["actions"]), 0)

    def test_move_with_multiple(self):
        preset = {"connections": [{"from": "A", "to": "C", "id": "1"}, {"from": "X", "to": "Y", "id": "2"}]}
        observed = [{"from": "A", "to": "B"}]
        res = self.planner.plan(preset, observed)
        actions = res["actions"]
        self.assertEqual(len(actions), 2)
        kinds = sorted([a["kind"] for a in actions])
        self.assertEqual(kinds, ["add", "move"])

if __name__ == '__main__':
    unittest.main()
