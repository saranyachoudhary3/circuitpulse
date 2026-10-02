"""Small deterministic modified-nodal-analysis solver for supported DC circuits."""

from __future__ import annotations

from typing import Any

import numpy as np

from logic.circuit_ir import CircuitIR, CircuitIRError


class DCSolverError(ValueError):
    pass


class LinearDCSolver:
    """Solve resistor/current/voltage-source circuits without an external tool.

    It intentionally rejects non-linear and dynamic parts instead of silently
    applying an invalid approximation.  ngspice remains the path for supported
    transient/non-linear templates; this solver makes simple operating-point
    checks available in offline, clean-boot demonstrations.
    """

    LINEAR_TYPES = {"resistor", "voltage_source", "supply", "current_source"}

    def solve(self, circuit: CircuitIR, ground_net: str) -> dict[str, Any]:
        ground = circuit.canonical_net(ground_net)
        unsupported = sorted({component.type for component in circuit.components.values() if component.type not in self.LINEAR_TYPES})
        if unsupported:
            return {"status": "INDETERMINATE", "reason": "Circuit has unsupported non-linear/dynamic component models.",
                    "unsupported_component_types": unsupported, "evidence_mode": "internal_linear_dc"}
        nets = sorted({circuit.canonical_net(net) for component in circuit.components.values() for net in component.pins.values()} - {ground})
        index = {net: position for position, net in enumerate(nets)}
        sources = [component for component in circuit.components.values() if component.type in {"voltage_source", "supply"} and component.raw.get("voltage_v") is not None]
        size = len(nets) + len(sources)
        if size == 0:
            raise DCSolverError("No solvable nodes or voltage sources were declared.")
        matrix = np.zeros((size, size), dtype=float)
        rhs = np.zeros(size, dtype=float)
        for component in circuit.components.values():
            if component.type == "resistor":
                self._stamp_resistor(matrix, index, circuit, component, ground)
            elif component.type == "current_source":
                self._stamp_current(rhs, index, circuit, component, ground)
        for source_index, component in enumerate(sources):
            self._stamp_voltage_source(matrix, rhs, index, circuit, component, ground, len(nets) + source_index)
        try:
            solution = np.linalg.solve(matrix, rhs)
        except np.linalg.LinAlgError as error:
            return {"status": "INDETERMINATE", "reason": "Circuit is floating, inconsistent, or singular for DC analysis.",
                    "evidence_mode": "internal_linear_dc", "detail": str(error)}
        voltages = {ground: 0.0} | {net: round(float(solution[position]), 6) for net, position in index.items()}
        return {"status": "PASS", "node_voltages_v": voltages, "evidence_mode": "internal_linear_dc"}

    @staticmethod
    def _two_pins(component) -> tuple[str, str]:
        nets = list(component.pins.values())
        if len(nets) != 2:
            raise DCSolverError(f"{component.type} {component.id} must have exactly two pins for linear DC analysis.")
        return nets[0], nets[1]

    @staticmethod
    def _node(index: dict[str, int], circuit: CircuitIR, net: str, ground: str) -> int | None:
        canonical = circuit.canonical_net(net)
        return None if canonical == ground else index[canonical]

    def _stamp_resistor(self, matrix, index, circuit, component, ground) -> None:
        try:
            resistance = float(component.raw["value_ohms"])
            if resistance <= 0:
                raise ValueError
        except (KeyError, TypeError, ValueError) as error:
            raise DCSolverError(f"Resistor {component.id} needs positive value_ohms.") from error
        first, second = self._two_pins(component)
        first_node, second_node = self._node(index, circuit, first, ground), self._node(index, circuit, second, ground)
        conductance = 1.0 / resistance
        if first_node is not None:
            matrix[first_node, first_node] += conductance
        if second_node is not None:
            matrix[second_node, second_node] += conductance
        if first_node is not None and second_node is not None:
            matrix[first_node, second_node] -= conductance
            matrix[second_node, first_node] -= conductance

    def _stamp_current(self, rhs, index, circuit, component, ground) -> None:
        try:
            current = float(component.raw["current_ma"]) / 1000.0
        except (KeyError, TypeError, ValueError) as error:
            raise DCSolverError(f"Current source {component.id} needs numeric current_ma.") from error
        positive, negative = self._two_pins(component)
        positive_node, negative_node = self._node(index, circuit, positive, ground), self._node(index, circuit, negative, ground)
        if positive_node is not None:
            rhs[positive_node] -= current
        if negative_node is not None:
            rhs[negative_node] += current

    def _stamp_voltage_source(self, matrix, rhs, index, circuit, component, ground, source_node) -> None:
        try:
            voltage = float(component.raw["voltage_v"])
        except (KeyError, TypeError, ValueError) as error:
            raise DCSolverError(f"Voltage source {component.id} needs numeric voltage_v.") from error
        positive = component.pins.get("positive") or component.pins.get("+")
        negative = component.pins.get("negative") or component.pins.get("-")
        if positive is None or negative is None:
            positive, negative = self._two_pins(component)
        positive_node, negative_node = self._node(index, circuit, positive, ground), self._node(index, circuit, negative, ground)
        if positive_node is not None:
            matrix[positive_node, source_node] += 1
            matrix[source_node, positive_node] += 1
        if negative_node is not None:
            matrix[negative_node, source_node] -= 1
            matrix[source_node, negative_node] -= 1
        rhs[source_node] = voltage
