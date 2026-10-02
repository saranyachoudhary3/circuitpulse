"""Deterministic trigger-to-response timing assertions for captured logic traces."""

from __future__ import annotations

from typing import Any

from logic.circuit_ir import CircuitIR, CircuitIRError


class TemporalAssertionError(ValueError):
    pass


class TemporalAssertionVerifier:
    """Verify each declared trigger edge against a reviewed response window."""

    def verify(self, circuit: CircuitIR, rule: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            trigger = circuit.canonical_net(rule["trigger_net"])
            response = circuit.canonical_net(rule["response_net"])
            trigger_direction = self._direction(rule.get("trigger_direction", "rising"))
            response_direction = self._direction(rule.get("response_direction", "rising"))
            minimum, maximum = float(rule.get("min_delay_us", 0)), float(rule["max_delay_us"])
            if minimum < 0 or maximum < minimum:
                raise TemporalAssertionError("Temporal delay window must be non-negative and ordered.")
            transitions = self._transitions(circuit)
            triggers = [item for item in transitions if item["net"] == trigger and item["direction"] == trigger_direction]
            responses = [item for item in transitions if item["net"] == response and item["direction"] == response_direction]
            if not triggers:
                return [self._finding("TEMPORAL_TRIGGER_UNOBSERVED", "warning", "No reviewed trigger edge was observed in the captured trace.", {"trigger_net": trigger, "direction": trigger_direction})]
            findings = []
            for event in triggers:
                candidates = [response_event for response_event in responses if response_event["time_us"] >= event["time_us"] + minimum]
                first = candidates[0] if candidates else None
                if first is None or first["time_us"] > event["time_us"] + maximum:
                    findings.append(self._finding("TEMPORAL_RESPONSE_TIMEOUT", "error", "No matching response edge occurred inside the reviewed timing window.",
                                                  {"trigger_time_us": event["time_us"], "min_delay_us": minimum, "max_delay_us": maximum,
                                                   "trigger_net": trigger, "response_net": response}))
                else:
                    delay = first["time_us"] - event["time_us"]
                    if not minimum <= delay <= maximum:
                        findings.append(self._finding("TEMPORAL_RESPONSE_OUT_OF_RANGE", "error", "Response edge occurred outside the reviewed timing window.",
                                                      {"trigger_time_us": event["time_us"], "response_time_us": first["time_us"], "delay_us": delay,
                                                       "min_delay_us": minimum, "max_delay_us": maximum}))
            return findings
        except (KeyError, TypeError, ValueError, CircuitIRError, TemporalAssertionError) as error:
            return [self._finding("TEMPORAL_ASSERTION_REQUIREMENT_INVALID", "error", str(error), {"requirement": rule})]

    @staticmethod
    def _transitions(circuit: CircuitIR) -> list[dict[str, Any]]:
        raw = circuit.measurements.get("digital_trace")
        if not isinstance(raw, list) or not raw:
            raise TemporalAssertionError("measurements.digital_trace must be a non-empty list.")
        levels, result, previous_time = {}, [], float("-inf")
        for item in raw:
            if not isinstance(item, dict) or not isinstance(item.get("levels"), dict):
                raise TemporalAssertionError("Each trace event requires time_us and levels.")
            time_us = float(item["time_us"])
            if time_us < previous_time:
                raise TemporalAssertionError("Temporal trace must be time ordered.")
            for raw_net, raw_value in item["levels"].items():
                net, value = circuit.canonical_net(raw_net), TemporalAssertionVerifier._level(raw_value)
                if value is None:
                    raise TemporalAssertionError("Temporal trace levels must be 0/1.")
                prior = levels.get(net)
                if prior is not None and prior != value:
                    result.append({"net": net, "direction": "rising" if value else "falling", "time_us": time_us})
                levels[net] = value
            previous_time = time_us
        return result

    @staticmethod
    def _direction(value: Any) -> str:
        if value not in {"rising", "falling"}:
            raise TemporalAssertionError("Temporal edge direction must be rising or falling.")
        return value

    @staticmethod
    def _level(value: Any) -> bool | None:
        return True if value in (True, 1) else False if value in (False, 0) else None

    @staticmethod
    def _finding(code: str, severity: str, message: str, evidence: dict[str, Any]) -> dict[str, Any]:
        return {"code": code, "severity": severity, "message": message, "evidence": evidence}
