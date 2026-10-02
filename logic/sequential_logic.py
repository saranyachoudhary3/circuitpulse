"""Trace-driven, fail-closed evaluation of reviewed sequential digital logic."""

from __future__ import annotations

from typing import Any

from logic.circuit_ir import CircuitIR, CircuitIRError


class SequentialLogicError(ValueError):
    pass


class SequentialLogicEvaluator:
    """Evaluate D/JK/T flip-flops from an explicit captured logic trace.

    A single camera frame cannot establish state, edge direction, or ordering.
    This evaluator therefore requires a time-ordered logic-analyzer/firmware
    trace. Unsupported sequential components remain indeterminate instead of
    being approximated as combinational gates.
    """

    SUPPORTED = {"d_flip_flop", "jk_flip_flop", "t_flip_flop"}

    def evaluate(self, circuit: CircuitIR, expected_final_levels: dict[str, Any] | None = None) -> dict[str, Any]:
        devices = [component for component in circuit.components.values() if component.type in self.SUPPORTED]
        unsupported = sorted({component.type for component in circuit.components.values()
                              if component.type.endswith("flip_flop") and component.type not in self.SUPPORTED
                              or component.type in {"counter", "shift_register", "latch", "oscillator"}})
        if not devices:
            raise SequentialLogicError("Sequential logic rule requires at least one supported flip-flop.")
        trace = self._trace(circuit)
        levels: dict[str, bool] = {}
        outputs: dict[str, bool | None] = {device.id: self._optional_bool(device.raw.get("initial_q")) for device in devices}
        for device in devices:
            if outputs[device.id] is not None:
                levels[circuit.canonical_net(device.pins[self._pin(device, "Q")])] = outputs[device.id]
        previous_clock: dict[str, bool | None] = {device.id: None for device in devices}
        last_input_change: dict[tuple[str, str], float] = {}
        last_clock_edge: dict[str, float] = {}
        findings: list[dict[str, Any]] = []
        transitions: list[dict[str, Any]] = []
        for event in trace:
            changed_nets = {net for net, value in event["levels"].items() if net in levels and levels[net] != value}
            for device in devices:
                hold = self._timing_value(device, "hold_time_us")
                edge_time = last_clock_edge.get(device.id)
                if hold and edge_time is not None and 0 <= event["time_us"] - edge_time < hold and changed_nets & set(self._input_nets(circuit, device)):
                    findings.append(self._finding("SEQUENTIAL_HOLD_TIME_VIOLATION", "critical", "Sequential input changed before the declared hold-time interval ended.", device.id,
                                                  {"time_us": event["time_us"], "clock_edge_time_us": edge_time, "required_hold_time_us": hold}))
            levels.update(event["levels"])
            for device in devices:
                for input_net in self._input_nets(circuit, device):
                    if input_net in event["levels"]:
                        last_input_change[(device.id, input_net)] = event["time_us"]
                output_pin = self._pin(device, "Q")
                output_net = circuit.canonical_net(device.pins[output_pin])
                reset = self._active_reset(circuit, device, levels)
                if reset is True:
                    if outputs[device.id] is not False:
                        outputs[device.id] = False
                        levels[output_net] = False
                        transitions.append({"time_us": event["time_us"], "device": device.id, "reason": "reset", "q": 0})
                    continue
                clock_net = circuit.canonical_net(device.pins[self._pin(device, "CLK")])
                clock = levels.get(clock_net)
                if clock is None:
                    continue
                edge = device.raw.get("clock_edge", "rising")
                if edge not in {"rising", "falling"}:
                    raise SequentialLogicError(f"{device.id} clock_edge must be rising or falling.")
                previous = previous_clock[device.id]
                previous_clock[device.id] = clock
                triggered = previous is not None and ((edge == "rising" and not previous and clock) or (edge == "falling" and previous and not clock))
                if not triggered:
                    continue
                setup = self._timing_value(device, "setup_time_us")
                setup_violations = [net for net in self._input_nets(circuit, device)
                                    if (device.id, net) in last_input_change and event["time_us"] - last_input_change[(device.id, net)] < setup]
                if setup_violations:
                    findings.append(self._finding("SEQUENTIAL_SETUP_TIME_VIOLATION", "critical", "Sequential input changed too close to the declared clock edge.", device.id,
                                                  {"time_us": event["time_us"], "required_setup_time_us": setup, "input_nets": setup_violations}))
                last_clock_edge[device.id] = event["time_us"]
                value = self._clock_value(circuit, device, levels, outputs[device.id])
                if value is None:
                    findings.append(self._finding("SEQUENTIAL_INPUT_UNRESOLVED", "warning", "Clock edge occurred with an unresolved sequential input or state.", device.id, event))
                    continue
                outputs[device.id] = value
                levels[output_net] = value
                transitions.append({"time_us": event["time_us"], "device": device.id, "reason": "clock_edge", "q": int(value)})
        for net, expected in (expected_final_levels or {}).items():
            expected_bool = self._bool(expected)
            if expected_bool is None:
                raise SequentialLogicError(f"Expected final level for {net} must be 0/1/false/true.")
            actual = levels.get(circuit.canonical_net(net))
            if actual is None:
                findings.append(self._finding("SEQUENTIAL_EXPECTATION_UNOBSERVED", "warning", "Expected sequential output could not be resolved from the trace.", None, {"net": net}))
            elif actual != expected_bool:
                findings.append(self._finding("SEQUENTIAL_EXPECTATION_MISMATCH", "error", "Final sequential logic level does not match the expected state.", None,
                                              {"net": net, "expected": int(expected_bool), "actual": int(actual)}))
        if unsupported:
            findings.append(self._finding("SEQUENTIAL_LOGIC_UNSUPPORTED", "warning", "Trace contains sequential devices without a reviewed state model.", None, {"types": unsupported}))
        status = "FAIL" if any(item["severity"] in {"critical", "error"} for item in findings) else ("INDETERMINATE" if findings else "PASS")
        return {"status": status, "levels": {net: int(value) for net, value in sorted(levels.items())}, "transitions": transitions,
                "findings": findings, "evidence_mode": "trace_driven_sequential_logic"}

    def _trace(self, circuit: CircuitIR) -> list[dict[str, Any]]:
        raw = circuit.measurements.get("digital_trace")
        if not isinstance(raw, list) or not raw:
            raise SequentialLogicError("measurements.digital_trace must be a non-empty list of captured events.")
        parsed, previous_time = [], -1.0
        for item in raw:
            if not isinstance(item, dict) or not isinstance(item.get("levels"), dict):
                raise SequentialLogicError("Every trace event needs time_us and a levels object.")
            try:
                time_us = float(item["time_us"])
            except (KeyError, TypeError, ValueError) as error:
                raise SequentialLogicError("Every trace event needs numeric time_us.") from error
            if time_us < previous_time:
                raise SequentialLogicError("digital_trace events must be time ordered.")
            levels = {}
            for net, value in item["levels"].items():
                parsed_value = self._bool(value)
                if not isinstance(net, str) or not net or parsed_value is None:
                    raise SequentialLogicError("Trace levels require non-empty net names and boolean values.")
                levels[circuit.canonical_net(net)] = parsed_value
            parsed.append({"time_us": time_us, "levels": levels})
            previous_time = time_us
        return parsed

    def _active_reset(self, circuit: CircuitIR, device, levels: dict[str, bool]) -> bool | None:
        reset_pin = device.raw.get("reset_pin")
        if reset_pin is None:
            return False
        if not isinstance(reset_pin, str) or reset_pin not in device.pins:
            raise SequentialLogicError(f"{device.id} reset_pin must name one of its pins.")
        active = self._bool(device.raw.get("reset_active", 0))
        if active is None:
            raise SequentialLogicError(f"{device.id} reset_active must be boolean.")
        value = levels.get(circuit.canonical_net(device.pins[reset_pin]))
        return None if value is None else value == active

    def _clock_value(self, circuit: CircuitIR, device, levels: dict[str, bool], prior_q: bool | None) -> bool | None:
        if device.type == "d_flip_flop":
            return levels.get(circuit.canonical_net(device.pins[self._pin(device, "D")]))
        if device.type == "t_flip_flop":
            toggle = levels.get(circuit.canonical_net(device.pins[self._pin(device, "T")]))
            return None if toggle is None or prior_q is None else prior_q ^ toggle
        if device.type == "jk_flip_flop":
            j = levels.get(circuit.canonical_net(device.pins[self._pin(device, "J")]))
            k = levels.get(circuit.canonical_net(device.pins[self._pin(device, "K")]))
            if j is None or k is None or prior_q is None:
                return None
            return prior_q if not j and not k else False if not j else True if not k else not prior_q
        raise SequentialLogicError(f"Unsupported sequential device: {device.type}")

    def _input_nets(self, circuit: CircuitIR, device) -> list[str]:
        pins = {"d_flip_flop": ("D",), "t_flip_flop": ("T",), "jk_flip_flop": ("J", "K")}[device.type]
        return [circuit.canonical_net(device.pins[self._pin(device, pin)]) for pin in pins]

    @staticmethod
    def _timing_value(device, name: str) -> float:
        raw = device.raw.get(name, 0.0)
        try:
            value = float(raw)
        except (TypeError, ValueError) as error:
            raise SequentialLogicError(f"{device.id} {name} must be a non-negative number.") from error
        if value < 0:
            raise SequentialLogicError(f"{device.id} {name} must be a non-negative number.")
        return value

    @staticmethod
    def _pin(device, name: str) -> str:
        if name not in device.pins:
            raise SequentialLogicError(f"{device.id} needs a {name} pin.")
        return name

    @staticmethod
    def _bool(value: Any) -> bool | None:
        return True if value in (True, 1) else False if value in (False, 0) else None

    def _optional_bool(self, value: Any) -> bool | None:
        if value is None:
            return None
        parsed = self._bool(value)
        if parsed is None:
            raise SequentialLogicError("initial_q must be 0/1/false/true when declared.")
        return parsed

    @staticmethod
    def _finding(code: str, severity: str, message: str, component_id: str | None, evidence: dict[str, Any]) -> dict[str, Any]:
        merged = {"component_id": component_id} if component_id else {}
        merged.update(evidence)
        return {"code": code, "severity": severity, "message": message, "evidence": merged}
