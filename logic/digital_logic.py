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

    GATES = {"and_gate", "or_gate", "not_gate", "nand_gate", "nor_gate", "xor_gate", "xnor_gate", "buffer_gate", "mux2", "tristate_buffer", "open_drain_buffer", "open_collector_output"}
    OUTPUT_NAMES = ("Y", "OUT", "out", "Q")

    def evaluate(self, circuit: CircuitIR, expected_levels: dict[str, Any] | None = None,
                 initial_levels: dict[str, Any] | None = None) -> dict[str, Any]:
        levels = self._initial_levels(circuit)
        net_drivers = {net: ["external"] for net in levels}
        
        for net, value in (initial_levels or {}).items():
            parsed = self._bool(value)
            if parsed is None:
                raise DigitalLogicError(f"Overridden logic level for {net} must be 0/1/false/true.")
            canonical = circuit.canonical_net(net)
            levels[canonical] = parsed
            if "external" not in net_drivers.get(canonical, []):
                net_drivers.setdefault(canonical, []).append("external")
                
        gates = [component for component in circuit.components.values() if component.type in self.GATES]
        unsupported = sorted({component.type for component in circuit.components.values()
                              if component.type.endswith("flip_flop") or component.type in {"counter", "oscillator", "latch"}})
        progress = True
        iterations = 0
        conflicts = []
        value_conflicts = set()
        
        while progress and iterations < max(1, len(gates) * 2):
            progress = False
            iterations += 1
            for gate in gates:
                outcome = self._gate_output(circuit, gate, levels)
                if outcome is None:
                    continue
                output_net, value = outcome
                
                if value == "Z":
                    continue
                    
                if output_net not in net_drivers:
                    net_drivers[output_net] = []
                    
                if gate not in net_drivers[output_net]:
                    net_drivers[output_net].append(gate)
                    progress = True
                    
                if output_net not in levels:
                    levels[output_net] = value
                    progress = True
                elif levels[output_net] != value:
                    if gate.type in {"open_drain_buffer", "open_collector_output"} and value is False:
                        levels[output_net] = False
                        progress = True
                    else:
                        value_conflicts.add(gate.id)

        for net, drivers in net_drivers.items():
            if len(drivers) > 1:
                all_open_drain = True
                for d in drivers:
                    if d != "external" and d.type not in {"open_drain_buffer", "open_collector_output"}:
                        all_open_drain = False
                        break
                if not all_open_drain:
                    for d in drivers:
                        if d != "external":
                            conflicts.append(d.id)
                else:
                    for d in drivers:
                        if d != "external" and d.id in value_conflicts:
                            value_conflicts.remove(d.id)
                            
        for gate_id in value_conflicts:
            if gate_id not in conflicts:
                conflicts.append(gate_id)
                
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
                "conflicts": sorted(set(conflicts)), "evidence_mode": "combinational_digital_logic"}

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

    def _gate_output(self, circuit: CircuitIR, gate, levels: dict[str, bool]) -> tuple[str, Any] | None:
        output_pin = self._output_pin(gate)
        if output_pin is None:
            raise DigitalLogicError(f"Gate {gate.id} needs Y, OUT, out, or Q output pin.")
            
        inputs = {pin: levels.get(circuit.canonical_net(net)) for pin, net in gate.pins.items() if pin != output_pin}
        
        if gate.type == "tristate_buffer":
            oe_pin = "OE" if "OE" in inputs else ("EN" if "EN" in inputs else None)
            if not oe_pin or "A" not in inputs:
                raise DigitalLogicError(f"tristate_buffer {gate.id} needs A and OE/EN inputs.")
            oe_val = inputs[oe_pin]
            if oe_val is None:
                return None
            if not oe_val:
                return circuit.canonical_net(gate.pins[output_pin]), "Z"
            a_val = inputs["A"]
            if a_val is None:
                return None
            return circuit.canonical_net(gate.pins[output_pin]), bool(a_val)
            
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
        elif gate.type in {"open_drain_buffer", "open_collector_output"}:
            in_val = self._one(gate, inputs)
            if in_val:
                value = False
            else:
                return circuit.canonical_net(gate.pins[output_pin]), "Z"
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
