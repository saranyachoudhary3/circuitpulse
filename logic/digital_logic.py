"""Conservative combinational digital-logic evaluator for typed circuits."""

from __future__ import annotations

from typing import Any

from logic.circuit_ir import CircuitIR


class DigitalLogicError(ValueError):
    pass


class DigitalLogicEvaluator:
    """Evaluate supported combinational gates until a stable fixed point.

    Sequential devices and feedback loops are reported as unresolved unless a
    dedicated temporal model is supplied. This prevents false claims about
    flip-flops, oscillators, counters, or analog threshold behaviour.
    """

    GATES = {"and_gate", "or_gate", "not_gate", "nand_gate", "nor_gate", "xor_gate", "xnor_gate", "buffer_gate", "mux2"}
    OUTPUT_NAMES = ("Y", "OUT", "out", "Q")

    def evaluate(self, circuit: CircuitIR, expected_levels: dict[str, Any] | None = None,
                 initial_levels: dict[str, Any] | None = None) -> dict[str, Any]:
        levels = self._initial_levels(circuit)
        for net, value in (initial_levels or {}).items():
            parsed = self._bool(value)
            if parsed is None:
                raise DigitalLogicError(f"Overridden logic level for {net} must be 0/1/false/true.")
            levels[circuit.canonical_net(net)] = parsed
        gates = [component for component in circuit.components.values() if component.type in self.GATES]
        unsupported = sorted({component.type for component in circuit.components.values()
                              if component.type.endswith("flip_flop") or component.type in {"counter", "oscillator", "latch"}})
        progress = True
        iterations = 0
        conflicts = []
        while progress and iterations < max(1, len(gates) * 2):
            progress = False
            iterations += 1
            for gate in gates:
                outcome = self._gate_output(circuit, gate, levels)
                if outcome is None:
                    continue
                output_net, value = outcome
                if output_net in levels and levels[output_net] != value:
                    conflicts.append(gate.id)
                elif output_net not in levels:
                    levels[output_net] = value
                    progress = True
        findings = []
        if conflicts:
            findings.append({"code": "DIGITAL_LOGIC_CONTENTION", "severity": "critical", "message": "Multiple declared logic drivers produce conflicting levels.", "evidence": {"components": sorted(set(conflicts))}})
        unresolved = [gate.id for gate in gates if self._gate_output(circuit, gate, levels) is None]
        if unresolved or unsupported:
            findings.append({"code": "DIGITAL_LOGIC_UNRESOLVED", "severity": "warning", "message": "Digital logic has unknown inputs, feedback, or unsupported sequential devices.", "evidence": {"gates": unresolved, "unsupported": unsupported}})
        for net, expected in (expected_levels or {}).items():
            canonical = circuit.canonical_net(net)
            expected_bool = self._bool(expected)
            if expected_bool is None:
                raise DigitalLogicError(f"Expected logic level for {net} must be 0/1/false/true.")
            if canonical not in levels:
                findings.append({"code": "DIGITAL_EXPECTATION_UNOBSERVED", "severity": "warning", "message": f"Expected logic net {net} could not be resolved.", "evidence": {"net": net}})
            elif levels[canonical] != expected_bool:
                findings.append({"code": "DIGITAL_EXPECTATION_MISMATCH", "severity": "error", "message": f"Logic net {net} does not match its expected level.", "evidence": {"net": net, "expected": int(expected_bool), "actual": int(levels[canonical])}})
        status = "FAIL" if any(item["severity"] in {"critical", "error"} for item in findings) else ("INDETERMINATE" if findings else "PASS")
        return {"status": status, "levels": {net: int(value) for net, value in sorted(levels.items())}, "findings": findings,
                "evidence_mode": "combinational_digital_logic"}

    def _initial_levels(self, circuit: CircuitIR) -> dict[str, bool]:
        levels: dict[str, bool] = {}
        raw = circuit.measurements.get("logic_levels", {})
        if not isinstance(raw, dict):
            raise DigitalLogicError("measurements.logic_levels must be an object.")
        for net, value in raw.items():
            parsed = self._bool(value)
            if parsed is None:
                raise DigitalLogicError(f"Logic level for {net} must be 0/1/false/true.")
            levels[circuit.canonical_net(net)] = parsed
        for component in circuit.components_of_type("logic_input"):
            output = self._output_pin(component)
            value = self._bool(component.raw.get("level"))
            if output is None or value is None:
                raise DigitalLogicError(f"logic_input {component.id} needs output pin and boolean level.")
            levels[circuit.canonical_net(component.pins[output])] = value
        return levels

    def _gate_output(self, circuit: CircuitIR, gate, levels: dict[str, bool]) -> tuple[str, bool] | None:
        output_pin = self._output_pin(gate)
        if output_pin is None:
            raise DigitalLogicError(f"Gate {gate.id} needs Y, OUT, out, or Q output pin.")
        inputs = {pin: levels.get(circuit.canonical_net(net)) for pin, net in gate.pins.items() if pin != output_pin}
        if any(value is None for value in inputs.values()):
            return None
        values = list(inputs.values())
        if gate.type == "and_gate": value = all(values)
        elif gate.type == "or_gate": value = any(values)
        elif gate.type == "not_gate": value = not self._one(gate, inputs)
        elif gate.type == "nand_gate": value = not all(values)
        elif gate.type == "nor_gate": value = not any(values)
        elif gate.type == "xor_gate": value = sum(values) % 2 == 1
        elif gate.type == "xnor_gate": value = sum(values) % 2 == 0
        elif gate.type == "buffer_gate": value = self._one(gate, inputs)
        elif gate.type == "mux2":
            if not {"A", "B", "S"}.issubset(inputs):
                raise DigitalLogicError(f"mux2 {gate.id} needs A, B, S, and output pins.")
            value = inputs["B"] if inputs["S"] else inputs["A"]
        else:
            return None
        return circuit.canonical_net(gate.pins[output_pin]), bool(value)

    @classmethod
    def _output_pin(cls, component) -> str | None:
        return next((name for name in cls.OUTPUT_NAMES if name in component.pins), None)

    @staticmethod
    def _one(gate, inputs: dict[str, bool]) -> bool:
        if len(inputs) != 1:
            raise DigitalLogicError(f"{gate.type} {gate.id} needs exactly one input.")
        return next(iter(inputs.values()))

    @staticmethod
    def _bool(value: Any) -> bool | None:
        if value in (True, 1):
            return True
        if value in (False, 0):
            return False
        return None
