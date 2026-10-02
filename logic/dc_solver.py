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

    LINEAR_TYPES = {"resistor", "voltage_source", "supply", "current_source", "capacitor", "inductor", "diode", "led"}
    DC_IGNORED_TYPES = {"capacitor"}
    DC_SHORT_TYPES = {"inductor"}
    DIODE_TYPES = {"diode", "led"}

    def solve(self, circuit: CircuitIR, ground_net: str) -> dict[str, Any]:
        ground = circuit.canonical_net(ground_net)
        unsupported = sorted({component.type for component in circuit.components.values() if component.type not in self.LINEAR_TYPES})
        if unsupported:
            return {"status": "INDETERMINATE", "reason": "Circuit has unsupported non-linear/dynamic component models.",
                    "unsupported_component_types": unsupported, "evidence_mode": "internal_linear_dc"}
        
        nets = set()
        for component in circuit.components.values():
            if component.type in self.DC_IGNORED_TYPES:
                continue
            for net in component.pins.values():
                nets.add(circuit.canonical_net(net))
            if component.type in self.DIODE_TYPES:
                nets.add(f"{component.id}_internal")
        nets.discard(ground)
        nets = sorted(nets)
        
        index = {net: position for position, net in enumerate(nets)}
        sources = [component for component in circuit.components.values() if component.type in {"voltage_source", "supply"} and component.raw.get("voltage_v") is not None]
        diode_components = [component for component in circuit.components.values() if component.type in self.DIODE_TYPES]
        size = len(nets) + len(sources) + len(diode_components)
        if size == 0:
            raise DCSolverError("No solvable nodes or voltage sources were declared.")
        matrix = np.zeros((size, size), dtype=float)
        rhs = np.zeros(size, dtype=float)
        for component in circuit.components.values():
            if component.type in self.DC_IGNORED_TYPES:
                continue
            elif component.type == "resistor":
                self._stamp_resistor(matrix, index, circuit, component, ground)
            elif component.type == "current_source":
                self._stamp_current(rhs, index, circuit, component, ground)
            elif component.type in self.DC_SHORT_TYPES:
                self._stamp_inductor(matrix, index, circuit, component, ground)
            elif component.type in self.DIODE_TYPES:
                source_index = len(nets) + len(sources) + diode_components.index(component)
                self._stamp_diode(matrix, rhs, index, circuit, component, ground, source_index)
        for source_index, component in enumerate(sources):
            self._stamp_voltage_source(matrix, rhs, index, circuit, component, ground, len(nets) + source_index)
        try:
            solution = np.linalg.solve(matrix, rhs)
        except np.linalg.LinAlgError as error:
            floating_nodes = [net for i, net in enumerate(nets) if i < len(nets) and matrix[i, i] == 0]
            diag_info = f" Possible floating nodes: {', '.join(floating_nodes)}." if floating_nodes else ""
            return {"status": "INDETERMINATE", "reason": f"Circuit is floating, inconsistent, or singular for DC analysis.{diag_info}",
                    "evidence_mode": "internal_linear_dc", "detail": str(error)}
        voltages = {ground: 0.0} | {net: round(float(solution[position]), 6) for net, position in index.items()}
        
        branch_currents = {}
        for component in circuit.components.values():
            if component.type == "resistor":
                r = float(component.raw["value_ohms"])
                p1, p2 = self._two_pins(component)
                v1, v2 = voltages.get(circuit.canonical_net(p1), 0.0), voltages.get(circuit.canonical_net(p2), 0.0)
                branch_currents[component.id] = {"i_a": round(abs(v1 - v2) / r, 6), "p_w": round(((v1 - v2) ** 2) / r, 6)}
                
        return {"status": "PASS", "node_voltages_v": voltages, "branch_currents": branch_currents, "evidence_mode": "internal_linear_dc"}

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

    def _stamp_inductor(self, matrix, index, circuit, component, ground) -> None:
        first, second = self._two_pins(component)
        first_node, second_node = self._node(index, circuit, first, ground), self._node(index, circuit, second, ground)
        conductance = 1.0 / 0.001
        if first_node is not None:
            matrix[first_node, first_node] += conductance
        if second_node is not None:
            matrix[second_node, second_node] += conductance
        if first_node is not None and second_node is not None:
            matrix[first_node, second_node] -= conductance
            matrix[second_node, first_node] -= conductance

    def _stamp_diode(self, matrix, rhs, index, circuit, component, ground, source_node) -> None:
        anode = next((net for pin, net in component.pins.items() if pin.lower() in ("anode", "+", "positive", "1")), None)
        cathode = next((net for pin, net in component.pins.items() if pin.lower() in ("cathode", "-", "negative", "2")), None)
        if anode is None or cathode is None:
            nets = list(component.pins.values())
            anode, cathode = nets[0], nets[1]
        
        vfwd = float(component.raw.get("forward_voltage_v", 2.0 if component.type == "led" else 0.7))
        r_series = 10.0
        internal_net = f"{component.id}_internal"
        
        anode_node = self._node(index, circuit, anode, ground)
        cathode_node = self._node(index, circuit, cathode, ground)
        internal_node = self._node(index, circuit, internal_net, ground)
        
        if anode_node is not None:
            matrix[anode_node, source_node] += 1
            matrix[source_node, anode_node] += 1
        if internal_node is not None:
            matrix[internal_node, source_node] -= 1
            matrix[source_node, internal_node] -= 1
        rhs[source_node] = vfwd
        
        conductance = 1.0 / r_series
        if internal_node is not None:
            matrix[internal_node, internal_node] += conductance
        if cathode_node is not None:
            matrix[cathode_node, cathode_node] += conductance
        if internal_node is not None and cathode_node is not None:
            matrix[internal_node, cathode_node] -= conductance
            matrix[cathode_node, internal_node] -= conductance
