"""Deterministic, evidence-based circuit checks.

Vision can suggest where a wire ends, but it cannot establish electrical
continuity from an RGB image.  This module deliberately accepts an explicit
netlist (from a schematic importer, a probe, or user-confirmed endpoints) and
returns ``INDETERMINATE`` when that evidence is missing.  It is the trustworthy
logic layer beneath the camera experience.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Iterable


PASS = "PASS"
FAIL = "FAIL"
INDETERMINATE = "INDETERMINATE"


@dataclass(frozen=True)
class Finding:
    """A machine-readable diagnostic returned by :class:`NetlistVerifier`."""

    code: str
    severity: str
    message: str
    evidence: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "evidence": self.evidence,
        }


class NetlistError(ValueError):
    """Raised when a submitted netlist cannot be evaluated safely."""


class NetlistVerifier:
    """Evaluate continuity and basic LED safety from a declared netlist.

    Input format::

        {
          "components": [
            {"id": "SUPPLY", "type": "supply",
             "pins": {"positive": "VCC", "negative": "GND"}},
            {"id": "R1", "type": "resistor", "value_ohms": 220,
             "pins": {"1": "VCC", "2": "LED_A"}},
            {"id": "D1", "type": "led",
             "pins": {"anode": "LED_A", "cathode": "GND"}}
          ]
        }

    Each pin maps to a net name.  Optional ``wires`` may connect two named
    nets; they are treated as zero-ohm conductors.  This intentionally small,
    portable format is easy to obtain from a schematic, a continuity tester,
    or a camera UI that asks the user to confirm ambiguous wire endpoints.
    """

    CONDUCTORS = {"wire", "jumper", "switch_closed", "fuse"}
    SUPPLIES = {"supply", "battery", "power_source", "arduino", "mcu"}
    MIN_LED_RESISTANCE_OHMS = 100

    def verify(self, netlist: dict[str, Any]) -> dict[str, Any]:
        components = self._normalise(netlist)
        findings: list[Finding] = []
        conductive_nets = self._conductive_graph(components, netlist.get("wires", []))
        positive_nets, ground_nets = self._supply_nets(components)

        if not positive_nets or not ground_nets:
            findings.append(Finding(
                "MISSING_REFERENCE",
                "warning",
                "No declared positive-and-ground reference was supplied; power-path checks are indeterminate.",
                {"positive_nets": sorted(positive_nets), "ground_nets": sorted(ground_nets)},
            ))

        for positive in positive_nets:
            for ground in ground_nets:
                if self._reachable(conductive_nets, positive, ground):
                    findings.append(Finding(
                        "DIRECT_POWER_SHORT",
                        "critical",
                        "Positive supply and ground are joined by a zero-ohm path.",
                        {"positive_net": positive, "ground_net": ground},
                    ))

        component_graph = self._component_graph(components, netlist.get("wires", []))
        for component in components:
            if component["type"] != "led":
                continue
            self._check_led(component, components, positive_nets, ground_nets, component_graph, findings)

        has_critical = any(f.severity == "critical" for f in findings)
        has_error = any(f.severity == "error" for f in findings)
        status = FAIL if has_critical or has_error else (INDETERMINATE if findings else PASS)
        return {
            "status": status,
            "findings": [finding.as_dict() for finding in findings],
            "summary": self._summary(status, findings),
            "checked_components": len(components),
            "evidence_mode": "declared_netlist",
        }

    def _normalise(self, netlist: dict[str, Any]) -> list[dict[str, Any]]:
        if not isinstance(netlist, dict):
            raise NetlistError("Netlist must be a JSON object.")
        raw_components = netlist.get("components")
        if not isinstance(raw_components, list) or not raw_components:
            raise NetlistError("Netlist requires a non-empty 'components' list.")

        ids: set[str] = set()
        components = []
        for raw in raw_components:
            if not isinstance(raw, dict):
                raise NetlistError("Each component must be an object.")
            identifier = raw.get("id")
            kind = raw.get("type")
            pins = raw.get("pins")
            if not isinstance(identifier, str) or not identifier.strip():
                raise NetlistError("Every component needs a non-empty string id.")
            if identifier in ids:
                raise NetlistError(f"Duplicate component id: {identifier}")
            if not isinstance(kind, str) or not kind.strip():
                raise NetlistError(f"Component {identifier} needs a type.")
            if not isinstance(pins, dict) or not pins:
                raise NetlistError(f"Component {identifier} needs a non-empty pins object.")
            if any(not isinstance(net, str) or not net.strip() for net in pins.values()):
                raise NetlistError(f"Component {identifier} has an invalid net name.")
            ids.add(identifier)
            components.append({
                "id": identifier,
                "type": kind.lower(),
                "pins": dict(pins),
                "value_ohms": raw.get("value_ohms"),
            })
        return components

    def _conductive_graph(self, components: Iterable[dict[str, Any]], wires: Any) -> dict[str, set[str]]:
        graph: dict[str, set[str]] = defaultdict(set)
        for wire in self._normalise_wires(wires):
            self._connect(graph, wire["from"], wire["to"])
        for component in components:
            if component["type"] in self.CONDUCTORS:
                self._connect_all(graph, component["pins"].values())
        return graph

    def _component_graph(self, components: Iterable[dict[str, Any]], wires: Any) -> dict[str, list[tuple[str, str | None]]]:
        """Graph edges carry their component ID; wires carry ``None``."""
        graph: dict[str, list[tuple[str, str | None]]] = defaultdict(list)
        for wire in self._normalise_wires(wires):
            self._edge(graph, wire["from"], wire["to"], None)
        for component in components:
            pins = list(component["pins"].values())
            if len(pins) >= 2:
                for index, first in enumerate(pins[:-1]):
                    for second in pins[index + 1:]:
                        self._edge(graph, first, second, component["id"])
        return graph

    @staticmethod
    def _normalise_wires(wires: Any) -> list[dict[str, str]]:
        if wires is None:
            return []
        if not isinstance(wires, list):
            raise NetlistError("'wires' must be a list when provided.")
        normalised = []
        for wire in wires:
            if not isinstance(wire, dict) or not isinstance(wire.get("from"), str) or not isinstance(wire.get("to"), str):
                raise NetlistError("Every wire requires string 'from' and 'to' nets.")
            normalised.append({"from": wire["from"], "to": wire["to"]})
        return normalised

    def _supply_nets(self, components: Iterable[dict[str, Any]]) -> tuple[set[str], set[str]]:
        positive, ground = set(), set()
        for component in components:
            pins = component["pins"]
            if component["type"] in self.SUPPLIES:
                for name, net in pins.items():
                    lowered = name.lower()
                    if lowered in {"positive", "vcc", "5v", "3v3", "+"}:
                        positive.add(net)
                    elif lowered in {"negative", "ground", "gnd", "-"}:
                        ground.add(net)
        return positive, ground

    def _check_led(self, led: dict[str, Any], components: list[dict[str, Any]], positive_nets: set[str], ground_nets: set[str], graph: dict[str, list[tuple[str, str | None]]], findings: list[Finding]) -> None:
        anode = led["pins"].get("anode") or led["pins"].get("+")
        cathode = led["pins"].get("cathode") or led["pins"].get("-")
        if not anode or not cathode:
            findings.append(Finding("LED_PIN_DATA_MISSING", "error", f"LED {led['id']} must declare anode and cathode nets.", {"component": led["id"]}))
            return
        # A layout without both declared references cannot establish a power
        # path; avoid turning absent evidence into a false safety failure.
        if not positive_nets or not ground_nets:
            return
        if positive_nets and not self._has_path(graph, anode, positive_nets):
            findings.append(Finding("LED_NO_SOURCE_PATH", "error", f"LED {led['id']} anode has no path to declared positive supply.", {"component": led["id"], "anode_net": anode}))
        if ground_nets and not self._has_path(graph, cathode, ground_nets):
            findings.append(Finding("LED_NO_RETURN_PATH", "error", f"LED {led['id']} cathode has no path to declared ground.", {"component": led["id"], "cathode_net": cathode}))
        resistors = [component for component in components if component["type"] == "resistor"]
        resistor_ids = {component["id"] for component in resistors}
        if not positive_nets or not self._has_path(graph, anode, positive_nets, required_component_ids=resistor_ids):
            findings.append(Finding(
                "LED_CURRENT_LIMITER_MISSING",
                "critical",
                f"LED {led['id']} has no resistor on its path to positive supply.",
                {"component": led["id"], "anode_net": anode, "minimum_recommended_ohms": 150},
            ))
            return

        safe_resistor_ids = {
            resistor["id"] for resistor in resistors
            if isinstance(resistor["value_ohms"], (int, float))
            and resistor["value_ohms"] >= self.MIN_LED_RESISTANCE_OHMS
        }
        if self._has_path(graph, anode, positive_nets, required_component_ids=safe_resistor_ids):
            return
        if any(resistor["value_ohms"] is None for resistor in resistors):
            findings.append(Finding(
                "LED_CURRENT_LIMITER_VALUE_UNKNOWN",
                "warning",
                f"LED {led['id']} has a series resistor, but its resistance is unknown.",
                {"component": led["id"], "minimum_recommended_ohms": self.MIN_LED_RESISTANCE_OHMS},
            ))
        else:
            findings.append(Finding(
                "LED_CURRENT_LIMITER_TOO_LOW",
                "error",
                f"LED {led['id']} has no series resistor of at least {self.MIN_LED_RESISTANCE_OHMS} ohms.",
                {"component": led["id"], "minimum_recommended_ohms": self.MIN_LED_RESISTANCE_OHMS},
            ))

    @staticmethod
    def _connect(graph: dict[str, set[str]], first: str, second: str) -> None:
        graph[first].add(second)
        graph[second].add(first)

    def _connect_all(self, graph: dict[str, set[str]], nets: Iterable[str]) -> None:
        unique = list(dict.fromkeys(nets))
        for index, first in enumerate(unique[:-1]):
            for second in unique[index + 1:]:
                self._connect(graph, first, second)

    @staticmethod
    def _edge(graph: dict[str, list[tuple[str, str | None]]], first: str, second: str, component_id: str | None) -> None:
        graph[first].append((second, component_id))
        graph[second].append((first, component_id))

    @staticmethod
    def _reachable(graph: dict[str, set[str]], start: str, target: str) -> bool:
        queue, visited = deque([start]), {start}
        while queue:
            net = queue.popleft()
            if net == target:
                return True
            for neighbour in graph.get(net, set()):
                if neighbour not in visited:
                    visited.add(neighbour)
                    queue.append(neighbour)
        return False

    def _has_path(self, graph: dict[str, list[tuple[str, str | None]]], start: str, targets: set[str], required_component_ids: set[str] | None = None) -> bool:
        requires_component = required_component_ids is not None
        required_ids = required_component_ids or set()
        queue = deque([(start, False)])
        visited = {(start, False)}
        while queue:
            net, passed_required = queue.popleft()
            if net in targets and (not requires_component or passed_required):
                return True
            for neighbour, component_id in graph.get(net, []):
                next_passed = passed_required or component_id in required_ids
                state = (neighbour, next_passed)
                if state not in visited:
                    visited.add(state)
                    queue.append(state)
        return False

    @staticmethod
    def _summary(status: str, findings: list[Finding]) -> str:
        if status == PASS:
            return "Declared netlist passes the implemented continuity and LED-safety checks."
        if status == INDETERMINATE:
            return "The netlist is structurally valid, but lacks enough reference data for every power-path check."
        return f"{len(findings)} issue(s) found in declared circuit connectivity."
