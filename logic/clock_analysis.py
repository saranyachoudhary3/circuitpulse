"""Clock frequency, duty-cycle, and jitter checks from timestamped logic traces."""

from __future__ import annotations

from statistics import mean
from typing import Any

from logic.circuit_ir import CircuitIR, CircuitIRError


class ClockAnalysisError(ValueError):
    pass


class ClockAnalyzer:
    """Measure only complete cycles represented by an explicit analyzer trace."""

    def evaluate(self, circuit: CircuitIR, rule: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            net = circuit.canonical_net(rule["clock_net"])
            trace = self._trace(circuit)
            rises, falls = self._edges(trace, net)
            if len(rises) < 2:
                return [self._finding("CLOCK_MEASUREMENT_UNAVAILABLE", "warning", "Clock trace needs at least two rising edges for frequency verification.", {"clock_net": net})]
            periods = [later - earlier for earlier, later in zip(rises, rises[1:])]
            if any(period <= 0 for period in periods):
                raise ClockAnalysisError("Clock rising-edge periods must be positive.")
            average_period = mean(periods)
            frequency = 1_000_000 / average_period
            findings = []
            if "frequency_range_hz" in rule:
                low, high = self._range(rule, "frequency_range_hz")
                if not low <= frequency <= high:
                    findings.append(self._finding("CLOCK_FREQUENCY_OUT_OF_RANGE", "error", "Measured clock frequency is outside the reviewed range.",
                                                  {"clock_net": net, "frequency_hz": frequency, "min_hz": low, "max_hz": high}))
            if "max_period_jitter_us" in rule:
                jitter = max(abs(period - average_period) for period in periods)
                maximum = float(rule["max_period_jitter_us"])
                if maximum < 0:
                    raise ClockAnalysisError("max_period_jitter_us must be non-negative.")
                if jitter > maximum:
                    findings.append(self._finding("CLOCK_JITTER_EXCEEDED", "error", "Measured edge-to-edge clock jitter exceeds the reviewed limit.",
                                                  {"clock_net": net, "jitter_us": jitter, "max_jitter_us": maximum, "periods_us": periods}))
            duty_cycles = self._duty_cycles(rises, falls)
            if "duty_cycle_range" in rule:
                if not duty_cycles:
                    findings.append(self._finding("CLOCK_DUTY_UNAVAILABLE", "warning", "Trace does not contain complete high intervals for duty-cycle verification.", {"clock_net": net}))
                else:
                    low, high = self._range(rule, "duty_cycle_range")
                    if low < 0 or high > 1:
                        raise ClockAnalysisError("duty_cycle_range must be within 0 to 1.")
                    actual_min, actual_max = min(duty_cycles), max(duty_cycles)
                    if actual_min < low or actual_max > high:
                        findings.append(self._finding("CLOCK_DUTY_OUT_OF_RANGE", "error", "Measured clock duty cycle is outside the reviewed range.",
                                                      {"clock_net": net, "duty_cycle_min": actual_min, "duty_cycle_max": actual_max, "min": low, "max": high}))
            return findings
        except (KeyError, TypeError, ValueError, CircuitIRError, ClockAnalysisError) as error:
            return [self._finding("CLOCK_REQUIREMENT_INVALID", "error", str(error), {"requirement": rule})]

    @staticmethod
    def _trace(circuit: CircuitIR) -> list[dict[str, Any]]:
        raw = circuit.measurements.get("digital_trace")
        if not isinstance(raw, list) or not raw:
            raise ClockAnalysisError("measurements.digital_trace must be a non-empty list.")
        result, previous = [], float("-inf")
        for item in raw:
            if not isinstance(item, dict) or not isinstance(item.get("levels"), dict):
                raise ClockAnalysisError("Every trace event needs time_us and levels.")
            time_us = float(item["time_us"])
            if time_us < previous:
                raise ClockAnalysisError("Clock trace must be time ordered.")
            result.append({"time_us": time_us, "levels": {circuit.canonical_net(net): value for net, value in item["levels"].items()}})
            previous = time_us
        return result

    @staticmethod
    def _edges(trace: list[dict[str, Any]], net: str) -> tuple[list[float], list[float]]:
        level, rises, falls = None, [], []
        for event in trace:
            if net not in event["levels"]:
                continue
            value = event["levels"][net]
            if value not in (0, 1, False, True):
                raise ClockAnalysisError("Clock trace levels must be 0/1.")
            current = int(value)
            if level == 0 and current == 1:
                rises.append(event["time_us"])
            elif level == 1 and current == 0:
                falls.append(event["time_us"])
            level = current
        return rises, falls

    @staticmethod
    def _duty_cycles(rises: list[float], falls: list[float]) -> list[float]:
        result = []
        for left, right in zip(rises, rises[1:]):
            fall = next((time for time in falls if left < time < right), None)
            if fall is not None and right > left:
                result.append((fall - left) / (right - left))
        return result

    @staticmethod
    def _range(rule: dict[str, Any], key: str) -> tuple[float, float]:
        try:
            low, high = float(rule[key][0]), float(rule[key][1])
        except (KeyError, TypeError, ValueError, IndexError) as error:
            raise ClockAnalysisError(f"{key} must be [minimum, maximum].") from error
        if low > high:
            raise ClockAnalysisError(f"{key} is reversed.")
        return low, high

    @staticmethod
    def _finding(code: str, severity: str, message: str, evidence: dict[str, Any]) -> dict[str, Any]:
        return {"code": code, "severity": severity, "message": message, "evidence": evidence}
