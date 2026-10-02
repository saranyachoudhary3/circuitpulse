"""Clocked finite-state-machine verification from sampled logic-analyzer traces."""

from __future__ import annotations

from typing import Any

from logic.circuit_ir import CircuitIR, CircuitIRError


class StateMachineError(ValueError):
    pass


class StateMachineVerifier:
    """Compare each observed clock transition with an explicit state table."""

    MAX_TRANSITIONS = 1024

    def verify(self, circuit: CircuitIR, rule: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            clock = circuit.canonical_net(rule["clock_net"])
            state_names, state_nets = self._nets(circuit, rule["state_nets"], "state_nets")
            input_names, input_nets = self._nets(circuit, rule.get("input_nets", []), "input_nets", allow_empty=True)
            edge = rule.get("clock_edge", "rising")
            settle = float(rule.get("settle_max_us", 0))
            if edge not in {"rising", "falling"} or settle < 0:
                raise StateMachineError("clock_edge must be rising/falling and settle_max_us must be non-negative.")
            table = self._table(rule.get("transitions"), state_names, input_names)
            snapshots = self._snapshots(circuit)
            if len(snapshots) > self.MAX_TRANSITIONS * 20:
                raise StateMachineError("State-machine trace has too many events for one assertion.")
            findings = []
            clock_level = None
            checked = 0
            for index, (time_us, before, after) in enumerate(snapshots):
                current = after.get(clock)
                triggered = clock_level is not None and current is not None and ((edge == "rising" and not clock_level and current) or (edge == "falling" and clock_level and not current))
                clock_level = current if current is not None else clock_level
                if not triggered:
                    continue
                prior_state = self._values(before, state_nets)
                inputs = self._values(after, input_nets)
                if prior_state is None or inputs is None:
                    findings.append(self._finding("STATE_MACHINE_SAMPLE_UNAVAILABLE", "warning", "Clock edge lacks complete prior state or input levels.", {"time_us": time_us}))
                    continue
                expected = table.get((prior_state, inputs))
                if expected is None:
                    findings.append(self._finding("STATE_MACHINE_TRANSITION_UNDECLARED", "error", "Observed state/input pair has no reviewed state-table transition.",
                                                  {"time_us": time_us, "state": prior_state, "inputs": inputs}))
                    continue
                final = self._settled_state(snapshots, index, time_us + settle, state_nets)
                if final is None:
                    findings.append(self._finding("STATE_MACHINE_SETTLE_UNAVAILABLE", "warning", "No complete state sample was captured inside the reviewed settling window.",
                                                  {"time_us": time_us, "settle_max_us": settle}))
                    continue
                checked += 1
                if final != expected:
                    findings.append(self._finding("STATE_MACHINE_TRANSITION_MISMATCH", "error", "Captured next state differs from the reviewed state transition.",
                                                  {"time_us": time_us, "prior_state": prior_state, "inputs": inputs, "expected_next_state": expected, "actual_next_state": final}))
            if checked == 0 and not findings:
                findings.append(self._finding("STATE_MACHINE_CLOCK_UNOBSERVED", "warning", "No reviewed clock edge was found in the state-machine trace.", {"clock_net": clock, "edge": edge}))
            return findings
        except (KeyError, TypeError, ValueError, CircuitIRError, StateMachineError) as error:
            return [self._finding("STATE_MACHINE_REQUIREMENT_INVALID", "error", str(error), {"requirement": rule})]

    @staticmethod
    def _nets(circuit: CircuitIR, raw: Any, name: str, allow_empty: bool = False) -> tuple[list[str], list[str]]:
        if not isinstance(raw, list) or (not raw and not allow_empty) or not all(isinstance(net, str) and net for net in raw):
            raise StateMachineError(f"{name} must be {'a possibly empty' if allow_empty else 'a non-empty'} list of net names.")
        nets = [circuit.canonical_net(net) for net in raw]
        if len(set(nets)) != len(nets):
            raise StateMachineError(f"{name} must be electrically distinct.")
        return list(raw), nets

    @staticmethod
    def _table(raw: Any, state_names: list[str], input_names: list[str]) -> dict[tuple[tuple[int, ...], tuple[int, ...]], tuple[int, ...]]:
        if not isinstance(raw, list) or not raw or len(raw) > StateMachineVerifier.MAX_TRANSITIONS:
            raise StateMachineError(f"transitions must contain 1 to {StateMachineVerifier.MAX_TRANSITIONS} rows.")
        table = {}
        for row in raw:
            if not isinstance(row, dict):
                raise StateMachineError("Every state transition must be an object.")
            state = StateMachineVerifier._row_values(row.get("state"), state_names, "state")
            inputs = StateMachineVerifier._row_values(row.get("inputs", {}), input_names, "inputs")
            next_state = StateMachineVerifier._row_values(row.get("next_state"), state_names, "next_state")
            key = (state, inputs)
            if key in table:
                raise StateMachineError("State transition table has a duplicate state/input row.")
            table[key] = next_state
        return table

    @staticmethod
    def _row_values(raw: Any, nets: list[str], name: str) -> tuple[int, ...]:
        if not isinstance(raw, dict):
            raise StateMachineError(f"Transition {name} must be an object keyed by reviewed net.")
        # Table keys use caller-provided names, but canonicalized net IDs are
        # intentionally also accepted for explicit imported netlists.
        if len(raw) != len(nets):
            raise StateMachineError(f"Transition {name} must cover every declared net exactly once.")
        values = []
        for net in nets:
            candidates = [value for key, value in raw.items() if key == net]
            if len(candidates) != 1:
                raise StateMachineError(f"Transition {name} is missing reviewed net {net}.")
            value = candidates[0]
            if value not in (0, 1, False, True):
                raise StateMachineError(f"Transition {name} values must be 0/1.")
            values.append(int(value))
        return tuple(values)

    @staticmethod
    def _snapshots(circuit: CircuitIR) -> list[tuple[float, dict[str, int], dict[str, int]]]:
        raw = circuit.measurements.get("digital_trace")
        if not isinstance(raw, list) or not raw:
            raise StateMachineError("measurements.digital_trace must be a non-empty list.")
        levels, snapshots, previous = {}, [], float("-inf")
        for item in raw:
            if not isinstance(item, dict) or not isinstance(item.get("levels"), dict):
                raise StateMachineError("Each trace event requires time_us and levels.")
            time_us = float(item["time_us"])
            if time_us < previous:
                raise StateMachineError("State-machine trace must be time ordered.")
            before = dict(levels)
            for net, value in item["levels"].items():
                if value not in (0, 1, False, True):
                    raise StateMachineError("State-machine trace levels must be 0/1.")
                levels[circuit.canonical_net(net)] = int(value)
            snapshots.append((time_us, before, dict(levels)))
            previous = time_us
        return snapshots

    @staticmethod
    def _values(levels: dict[str, int], nets: list[str]) -> tuple[int, ...] | None:
        return tuple(levels[net] for net in nets) if all(net in levels for net in nets) else None

    def _settled_state(self, snapshots, index: int, deadline: float, state_nets: list[str]) -> tuple[int, ...] | None:
        final = None
        for time_us, _, after in snapshots[index + 1:]:
            if time_us > deadline:
                break
            value = self._values(after, state_nets)
            if value is not None:
                final = value
        return final

    @staticmethod
    def _finding(code: str, severity: str, message: str, evidence: dict[str, Any]) -> dict[str, Any]:
        return {"code": code, "severity": severity, "message": message, "evidence": evidence}
