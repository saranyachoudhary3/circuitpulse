"""Typed, canonical circuit representation for deterministic analysis.

Images, user confirmations, EDA imports, and instruments may all describe a
circuit differently.  This module reduces them to one conservative electrical
representation without guessing omitted values or connections.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class CircuitIRError(ValueError):
    pass


class _UnionFind:
    POWER_NETS = frozenset({'GND', 'gnd', 'VCC', 'vcc', '5V', '5v', '3V3', '3v3', 'VBUS', 'VIN', 'GROUND'})

    def __init__(self):
        self.parent: dict[str, str] = {}

    def find(self, item: str) -> str:
        self.parent.setdefault(item, item)
        if self.parent[item] != item:
            self.parent[item] = self.find(self.parent[item])
        return self.parent[item]

    def union(self, first: str, second: str) -> None:
        first_root, second_root = self.find(first), self.find(second)
        if first_root != second_root:
            # Prefer well-known power net names as canonical roots
            if second_root in self.POWER_NETS and first_root not in self.POWER_NETS:
                self.parent[first_root] = second_root
            else:
                self.parent[second_root] = first_root


@dataclass(frozen=True)
class CircuitComponent:
    id: str
    type: str
    pins: dict[str, str]
    raw: dict[str, Any]


class CircuitIR:
    """Validated circuit object with canonical electrical nets.

    Input uses the existing ``components``/``wires`` netlist shape plus optional
    ``requirements`` and ``measurements``. Wires join named electrical nets;
    components deliberately do not become conductors unless a specific rule
    models them.
    """

    SCHEMA_VERSION = 1

    def __init__(self, payload: dict[str, Any]):
        if not isinstance(payload, dict):
            raise CircuitIRError("Circuit payload must be an object.")
        version = payload.get("schema_version", self.SCHEMA_VERSION)
        if version != self.SCHEMA_VERSION:
            raise CircuitIRError("Circuit payload must use schema_version 1.")
        raw_components = payload.get("components")
        if not isinstance(raw_components, list) or not raw_components:
            raise CircuitIRError("Circuit payload requires a non-empty components list.")
        self.components: dict[str, CircuitComponent] = {}
        self._nets = _UnionFind()
        for raw in raw_components:
            component = self._component(raw)
            if component.id in self.components:
                raise CircuitIRError(f"Duplicate component id: {component.id}")
            self.components[component.id] = component
            for net in component.pins.values():
                self._nets.find(net)
        wires = payload.get("wires", [])
        if not isinstance(wires, list):
            raise CircuitIRError("wires must be a list.")
        for wire in wires:
            if not isinstance(wire, dict) or not all(isinstance(wire.get(key), str) and wire[key] for key in ("from", "to")):
                raise CircuitIRError("Every wire needs non-empty from and to net names.")
            if wire["from"] == wire["to"]:
                continue  # Skip degenerate self-loop wires
            self._nets.union(wire["from"], wire["to"])
        self.requirements = self._objects(payload.get("requirements", []), "requirements")
        self.measurements = payload.get("measurements", {})
        if not isinstance(self.measurements, dict):
            raise CircuitIRError("measurements must be an object.")

    @staticmethod
    def _objects(value: Any, name: str) -> list[dict[str, Any]]:
        if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
            raise CircuitIRError(f"{name} must be a list of objects.")
        return value

    @staticmethod
    def _component(raw: Any) -> CircuitComponent:
        if not isinstance(raw, dict):
            raise CircuitIRError("Every component must be an object.")
        identifier, kind, pins = raw.get("id"), raw.get("type"), raw.get("pins")
        if not isinstance(identifier, str) or not identifier:
            raise CircuitIRError("Every component needs a non-empty id.")
        if not isinstance(kind, str) or not kind:
            raise CircuitIRError(f"Component {identifier} needs a type.")
        if not isinstance(pins, dict) or not pins or not all(isinstance(pin, str) and pin and isinstance(net, str) and net for pin, net in pins.items()):
            raise CircuitIRError(f"Component {identifier} needs non-empty string pin-to-net mappings.")
        return CircuitComponent(identifier, kind.lower(), dict(pins), dict(raw))

    def canonical_net(self, net: str) -> str:
        if not isinstance(net, str) or not net:
            raise CircuitIRError("Net names must be non-empty strings.")
        return self._nets.find(net)

    def same_net(self, first: str, second: str) -> bool:
        return self.canonical_net(first) == self.canonical_net(second)

    def component(self, identifier: str) -> CircuitComponent:
        try:
            return self.components[identifier]
        except KeyError as error:
            raise CircuitIRError(f"Unknown component: {identifier}") from error

    def pin_net(self, component_id: str, pin: str) -> str:
        component = self.component(component_id)
        if pin not in component.pins:
            raise CircuitIRError(f"Component {component_id} has no pin {pin}.")
        return self.canonical_net(component.pins[pin])

    def components_of_type(self, kind: str) -> list[CircuitComponent]:
        return [component for component in self.components.values() if component.type == kind.lower()]
