import unittest

from logic.catalog import ComponentCatalog, PresetCatalog
from logic.netlist import NetlistVerifier
from logic.logic_engine import CircuitLogicEngine
from logic.session import GraphSession, SessionError
from vision.topology import Terminal, TerminalMapper
from vision.runtime import choose_model
from vision.fiducials import MODULE_MARKER_IDS


class GraphSessionTests(unittest.TestCase):
    def setUp(self):
        self.presets = PresetCatalog()
        self.session = GraphSession(self.presets.get("led_blink"))

    def _attach_safe_led_netlist(self, session=None):
        session = session or self.session
        netlist = {
            "components": [
                {"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}},
                {"id": "R1", "type": "resistor", "value_ohms": 220, "pins": {"1": "VCC", "2": "LED_A"}},
                {"id": "D1", "type": "led", "pins": {"anode": "LED_A", "cathode": "GND"}},
            ]
        }
        report = NetlistVerifier().verify(netlist)
        state = session.state()
        terminal_nets = {"arduino:D13": "VCC", "bb:r7a": "VCC", "bb:r7e": "LED_A", "led:anode": "LED_A",
                         "led:cathode": "GND", "arduino:GND": "GND"}
        return session.attach_deterministic_verification(report, state["graph_revision"], state["graph_fingerprint"], terminal_nets, netlist)

    def test_new_session_is_incomplete_not_safe(self):
        state = self.session.state()
        self.assertEqual(state["status"], "INCOMPLETE")
        self.assertEqual(state["electrical_status"], "INCOMPLETE")
        self.assertEqual(state["next_action"]["kind"], "add")

    def test_confirmed_expected_graph_passes(self):
        for connection in self.session.preset["connections"]:
            state = self.session.confirm(connection["from"], connection["to"], True, connection.get("wire_color"))
        self.assertEqual(state["status"], "INDETERMINATE")
        state = self._attach_safe_led_netlist()
        self.assertEqual(state["status"], "PASS")
        self.assertEqual(state["next_action"]["kind"], "complete")

    def test_five_stable_visual_frames_create_unconfirmed_edge(self):
        for _ in range(5):
            state = self.session.observe([{"from": "arduino:D13", "to": "bb:r7a", "confidence": 0.9}])
        self.assertEqual(state["status"], "INDETERMINATE")
        self.assertIn("UNCONFIRMED_CONNECTION", {item["code"] for item in state["findings"]})

    def test_high_confidence_visual_graph_can_pass_after_stability(self):
        observations = [
            {"from": edge["from"], "to": edge["to"], "confidence": 0.99, "wire_color": edge.get("wire_color")}
            for edge in self.session.preset["connections"]
        ]
        for _ in range(5):
            state = self.session.observe(observations)
        self.assertEqual(state["status"], "INDETERMINATE")
        state = self._attach_safe_led_netlist()
        self.assertEqual(state["status"], "PASS")

    def test_removed_visual_wire_ages_out_after_complete_absent_frames(self):
        session = GraphSession(PresetCatalog().get("led_blink"))
        edge = {"from": "arduino:D13", "to": "bb:r7a", "confidence": 0.99}
        for _ in range(5):
            session.observe([edge])
        self.assertIn("arduino:D13 <-> bb:r7a", {item["id"] for item in session.state()["graph"]["observed"]})
        for _ in range(5):
            state = session.observe([])
        self.assertNotIn("arduino:D13 <-> bb:r7a", {item["id"] for item in state["graph"]["observed"]})

    def test_camera_loss_withholds_prior_verdict(self):
        session = GraphSession(PresetCatalog().get("led_blink"))
        for connection in session.preset["connections"]:
            session.confirm(connection["from"], connection["to"], True)
        self._attach_safe_led_netlist(session)
        self.assertEqual(session.state()["status"], "PASS")
        state = session.set_camera_available(False)
        self.assertEqual(state["status"], "REACQUIRING")
        self.assertEqual(state["next_action"]["kind"], "wait")

    def test_deterministic_report_requires_current_topology_revision(self):
        state = self.session.confirm("arduino:D13", "bb:r7a", True)
        old_graph_revision = state["graph_revision"]
        self.session.confirm("bb:r7e", "led:anode", True)
        report = NetlistVerifier().verify({
            "components": [{"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}}]
        })
        with self.assertRaises(SessionError):
            self.session.attach_deterministic_verification(report, old_graph_revision, "stale", {}, {})

    def test_failed_deterministic_report_is_a_fault(self):
        for connection in self.session.preset["connections"]:
            self.session.confirm(connection["from"], connection["to"], True)
        netlist = {
            "components": [
                {"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}},
                {"id": "R1", "type": "resistor", "value_ohms": 50, "pins": {"1": "VCC", "2": "LED_A"}},
                {"id": "D1", "type": "led", "pins": {"anode": "LED_A", "cathode": "GND"}},
            ]
        }
        unsafe = NetlistVerifier().verify(netlist)
        current = self.session.state()
        terminal_nets = {"arduino:D13": "VCC", "bb:r7a": "VCC", "bb:r7e": "LED_A", "led:anode": "LED_A",
                         "led:cathode": "GND", "arduino:GND": "GND"}
        state = self.session.attach_deterministic_verification(unsafe, current["graph_revision"], current["graph_fingerprint"], terminal_nets, netlist)
        self.assertEqual(state["status"], "FAULT")
        self.assertEqual(state["next_action"]["kind"], "repair")

    def test_netlist_must_bind_each_observed_wire_to_same_net(self):
        for connection in self.session.preset["connections"]:
            self.session.confirm(connection["from"], connection["to"], True)
        netlist = {"components": [{"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}}]}
        report = NetlistVerifier().verify(netlist)
        state = self.session.state()
        invalid_bindings = {terminal: "VCC" for terminal in ("arduino:D13", "bb:r7a", "bb:r7e", "led:anode", "led:cathode", "arduino:GND")}
        invalid_bindings["bb:r7a"] = "GND"
        with self.assertRaises(SessionError):
            self.session.attach_deterministic_verification(report, state["graph_revision"], state["graph_fingerprint"], invalid_bindings, netlist)

    def test_typed_root_cause_becomes_next_repair_action(self):
        for connection in self.session.preset["connections"]:
            self.session.confirm(connection["from"], connection["to"], True)
        netlist = {"components": [
            {"id": "SUPPLY", "type": "supply", "pins": {"positive": "VCC", "negative": "GND"}},
            {"id": "R1", "type": "resistor", "value_ohms": 220, "pins": {"1": "VCC", "2": "LED_A"}},
            {"id": "D1", "type": "led", "pins": {"anode": "LED_A", "cathode": "GND"}},
        ], "requirements": [{"kind": "gpio_output", "load_current_ma": 50, "max_current_ma": 20}]}
        report = CircuitLogicEngine().analyze(netlist)
        state = self.session.state()
        bindings = {"arduino:D13": "VCC", "bb:r7a": "VCC", "bb:r7e": "LED_A", "led:anode": "LED_A",
                    "led:cathode": "GND", "arduino:GND": "GND"}
        state = self.session.attach_deterministic_verification(report, state["graph_revision"], state["graph_fingerprint"], bindings, netlist)
        self.assertEqual(state["status"], "FAULT")
        self.assertIn("transistor or driver", state["next_action"]["instruction"])

    def test_direct_power_short_is_fault(self):
        state = self.session.confirm("arduino:5V", "arduino:GND", True, "red")
        self.assertEqual(state["status"], "FAULT")
        self.assertEqual(state["findings"][0]["code"], "DIRECT_POWER_SHORT")
        self.assertEqual(state["next_action"]["kind"], "remove")

    def test_catalogs_include_reviewed_demo_content(self):
        self.assertEqual(len(self.presets.list_public()), 6)
        self.assertGreaterEqual(len(ComponentCatalog().list_public()), 14)

    def test_module_identity_is_not_mistaken_for_measured_terminal_geometry(self):
        module = ComponentCatalog().get("arduino_uno")
        self.assertEqual(ComponentCatalog.terminal_layout_status(module), "LAYOUT_PENDING_PHYSICAL_MEASUREMENT")


class TerminalMapperTests(unittest.TestCase):
    def test_terminal_attachment_and_ambiguity(self):
        mapper = TerminalMapper(max_distance_mm=6, ambiguity_delta_mm=0.5)
        terminals = [Terminal("arduino:D13", 10, 10, 1), Terminal("arduino:D12", 20, 10, 1)]
        attached = mapper.attach((10.2, 10.1), terminals)
        self.assertEqual(attached["status"], "ATTACHED")
        ambiguous = mapper.attach((15, 10), terminals)
        self.assertEqual(ambiguous["status"], "AMBIGUOUS")

    def test_runtime_selector_uses_local_model_only(self):
        selection = choose_model(__import__("pathlib").Path(__file__).parent)
        self.assertTrue(selection.path.endswith((".pt", ".engine")))

    def test_every_printed_module_marker_has_a_reviewed_manifest(self):
        catalog = ComponentCatalog()
        for fiducial_id in MODULE_MARKER_IDS.values():
            self.assertIsNotNone(catalog.identify_fiducial(fiducial_id))


if __name__ == "__main__":
    unittest.main()
