"""Validate captured power/reset/enable sequencing for reviewed modules."""

from __future__ import annotations

from typing import Any

from logic.circuit_ir import CircuitIR, CircuitIRError


class PowerSequenceError(ValueError):
    pass


class PowerSequenceAnalyzer:
    """Assess explicit threshold crossings from an instrumented voltage trace."""

    def evaluate(self, circuit: CircuitIR, rule: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            events = self._events(circuit)
            power_net = circuit.canonical_net(rule["power_net"])
            power_threshold = float(rule["power_good_threshold_v"])
            if power_threshold <= 0:
                raise ValueError
            power_good_at = self._crossing(events, power_net, power_threshold, rising=True)
            if power_good_at is None:
                return [self._finding("POWER_SEQUENCE_POWER_NOT_GOOD", "critical", "Power rail never reached the reviewed power-good threshold in the captured sequence.",
                                      {"power_net": power_net, "threshold_v": power_threshold})]
            findings = []
            for signal in rule.get("signals", []):
                if not isinstance(signal, dict):
                    raise ValueError
                net = circuit.canonical_net(signal["net"])
                threshold = float(signal.get("threshold_v", 0.5))
                allowed_after = float(signal.get("min_after_power_good_us", 0))
                required_before = float(signal.get("max_before_power_good_us", float("inf")))
                direction = signal.get("direction", "rising")
                if direction not in {"rising", "falling"} or threshold < 0 or allowed_after < 0:
                    raise ValueError
                crossing = self._crossing(events, net, threshold, rising=direction == "rising")
                if crossing is None:
                    if signal.get("required", True):
                        findings.append(self._finding("POWER_SEQUENCE_SIGNAL_MISSING", "error", "Required reset/enable/data transition was absent from captured power sequence.",
                                                      {"net": net, "direction": direction, "threshold_v": threshold}))
                    continue
                delta = crossing - power_good_at
                if delta < allowed_after or delta > required_before:
                    findings.append(self._finding("POWER_SEQUENCE_ORDER_VIOLATION", "critical", "Captured reset/enable/data transition violates the reviewed rail-sequencing window.",
                                                  {"net": net, "power_good_at_us": power_good_at, "signal_crossing_at_us": crossing,
                                                   "delta_us": delta, "min_after_power_good_us": allowed_after,
                                                   "max_before_power_good_us": required_before, "direction": direction}))
            return findings
        except (KeyError, TypeError, ValueError, CircuitIRError, PowerSequenceError) as error:
            return [self._finding("POWER_SEQUENCE_REQUIREMENT_INVALID", "error", str(error), {"requirement": rule})]

    @staticmethod
    def _events(circuit: CircuitIR) -> list[dict[str, Any]]:
        raw = circuit.measurements.get("voltage_trace")
        if not isinstance(raw, list) or not raw:
            raise PowerSequenceError("measurements.voltage_trace must be a non-empty timestamped list.")
        events, previous = [], float("-inf")
        for item in raw:
            if not isinstance(item, dict) or not isinstance(item.get("voltages_v"), dict):
                raise PowerSequenceError("Every voltage trace event needs time_us and voltages_v.")
            try:
                time_us = float(item["time_us"])
            except (KeyError, TypeError, ValueError) as error:
                raise PowerSequenceError("Every voltage trace event needs numeric time_us.") from error
            if time_us < previous:
                raise PowerSequenceError("Voltage trace events must be time ordered.")
            voltages = {}
            for net, value in item["voltages_v"].items():
                if not isinstance(net, str) or not net:
                    raise PowerSequenceError("Voltage trace net names must be non-empty strings.")
                voltages[circuit.canonical_net(net)] = float(value)
            events.append({"time_us": time_us, "voltages_v": voltages})
            previous = time_us
        return events

    @staticmethod
    def _crossing(events: list[dict[str, Any]], net: str, threshold: float, rising: bool) -> float | None:
        previous = None
        for event in events:
            value = event["voltages_v"].get(net)
            if value is None:
                continue
            if previous is not None and ((rising and previous < threshold <= value) or (not rising and previous > threshold >= value)):
                return event["time_us"]
            previous = value
        return None

    @staticmethod
    def _finding(code: str, severity: str, message: str, evidence: dict[str, Any]) -> dict[str, Any]:
        return {"code": code, "severity": severity, "message": message, "evidence": evidence}
