"""Deterministic timing checks for supported first-order RC circuits."""

from __future__ import annotations

from math import exp, log
from typing import Any

from logic.circuit_ir import CircuitIR, CircuitIRError


class TemporalAnalysisError(ValueError):
    pass


class TemporalRangeError(TemporalAnalysisError):
    def __init__(self, code: str, message: str, evidence: dict[str, Any]):
        super().__init__(message)
        self.code = code
        self.evidence = evidence


class TemporalAnalyzer:
    """Analyze declared RC charging/discharging behavior.

    This supports only a reviewed, explicit first-order RC abstraction. It does
    not approximate op-amp oscillators, switching regulators, motors, or other
    complex dynamic circuits; those require a validated ngspice template or
    measured instrument trace.
    """

    def rc_timing(self, circuit: CircuitIR, rule: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            resistor = circuit.component(rule["resistor"])
            capacitor = circuit.component(rule["capacitor"])
            if resistor.type != "resistor" or capacitor.type != "capacitor":
                raise TemporalAnalysisError("RC timing rule must reference a resistor and capacitor.")
            resistance = float(resistor.raw["value_ohms"])
            capacitance_uf = float(capacitor.raw["value_uf"])
            if resistance <= 0 or capacitance_uf <= 0:
                raise TemporalAnalysisError("RC resistor/capacitor values must be positive.")
            tau_ms = resistance * capacitance_uf / 1000.0
            result: dict[str, Any] = {"tau_ms": round(tau_ms, 6)}
            if "target_fraction" in rule:
                fraction = float(rule["target_fraction"])
                if not 0 < fraction < 1:
                    raise TemporalAnalysisError("target_fraction must be strictly between 0 and 1.")
                result["time_to_target_ms"] = round(-tau_ms * log(1 - fraction), 6)
            if "elapsed_ms" in rule:
                elapsed = float(rule["elapsed_ms"])
                if elapsed < 0:
                    raise TemporalAnalysisError("elapsed_ms must be non-negative.")
                initial = float(rule.get("initial_voltage_v", 0.0))
                final = float(rule["final_voltage_v"])
                result["expected_voltage_v"] = round(final + (initial - final) * exp(-elapsed / tau_ms), 6)
            self._assert_range(result, rule)
            return []
        except TemporalRangeError as error:
            return [{"code": error.code, "severity": "critical", "message": str(error), "evidence": error.evidence}]
        except (KeyError, TypeError, ValueError, CircuitIRError, TemporalAnalysisError) as error:
            return [{"code": "RC_TIMING_REQUIREMENT_INVALID", "severity": "error", "message": str(error), "evidence": {"requirement": rule}}]

    @staticmethod
    def _assert_range(result: dict[str, Any], rule: dict[str, Any]) -> None:
        for key, result_key in (("tau_range_ms", "tau_ms"), ("time_to_target_range_ms", "time_to_target_ms"),
                                ("expected_voltage_range_v", "expected_voltage_v")):
            if key not in rule:
                continue
            try:
                minimum, maximum = float(rule[key][0]), float(rule[key][1])
                actual = result[result_key]
            except (TypeError, ValueError, KeyError, IndexError) as error:
                raise TemporalAnalysisError(f"{key} must be [minimum, maximum] and requires {result_key}.") from error
            if not minimum <= actual <= maximum:
                code = "RC_TIME_OUT_OF_RANGE" if result_key != "expected_voltage_v" else "RC_VOLTAGE_OUT_OF_RANGE"
                raise TemporalRangeError(code, f"Calculated {result_key}={actual} is outside [{minimum}, {maximum}].",
                                         {"actual": actual, "min": minimum, "max": maximum, "metric": result_key})
