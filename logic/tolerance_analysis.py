"""Worst-case component-tolerance checks for reviewed analog circuit rules."""

from __future__ import annotations

from itertools import product
from typing import Any

from logic.circuit_ir import CircuitIR, CircuitIRError


class ToleranceAnalysisError(ValueError):
    pass


class ToleranceAnalyzer:
    """Enumerate stated component extremes; never invent a tolerance class."""

    def voltage_divider(self, circuit: CircuitIR, rule: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            upper = circuit.component(rule["upper_resistor"])
            lower = circuit.component(rule["lower_resistor"])
            if upper.type != "resistor" or lower.type != "resistor":
                raise ToleranceAnalysisError("Voltage-divider tolerance rule must reference two resistors.")
            r1, r1_tol = self._component_value(upper, "value_ohms", "tolerance_fraction")
            r2, r2_tol = self._component_value(lower, "value_ohms", "tolerance_fraction")
            input_min, input_max = self._range(rule, "input_voltage_range_v")
            output_min, output_max = self._range(rule, "output_voltage_range_v")
            topology = {circuit.canonical_net(net) for net in upper.pins.values()} & {circuit.canonical_net(net) for net in lower.pins.values()}
            if not topology:
                raise ToleranceAnalysisError("Divider resistors do not share a declared midpoint net.")
            values = []
            for source, r1_actual, r2_actual in product((input_min, input_max), (r1 * (1 - r1_tol), r1 * (1 + r1_tol)), (r2 * (1 - r2_tol), r2 * (1 + r2_tol))):
                values.append(source * r2_actual / (r1_actual + r2_actual))
            actual_min, actual_max = min(values), max(values)
            evidence = {"worst_case_output_min_v": round(actual_min, 6), "worst_case_output_max_v": round(actual_max, 6),
                        "required_output_min_v": output_min, "required_output_max_v": output_max,
                        "input_voltage_range_v": [input_min, input_max],
                        "upper_resistor": upper.id, "lower_resistor": lower.id,
                        "upper_tolerance_fraction": r1_tol, "lower_tolerance_fraction": r2_tol}
            if actual_min < output_min or actual_max > output_max:
                return [self._finding("DIVIDER_TOLERANCE_OUT_OF_RANGE", "critical", "Worst-case resistor and source tolerance can move divider output outside its reviewed range.", evidence)]
            return []
        except (KeyError, TypeError, ValueError, CircuitIRError, ToleranceAnalysisError) as error:
            return [self._finding("DIVIDER_TOLERANCE_REQUIREMENT_INVALID", "error", str(error), {"requirement": rule})]

    def rc_timing(self, circuit: CircuitIR, rule: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            resistor = circuit.component(rule["resistor"])
            capacitor = circuit.component(rule["capacitor"])
            if resistor.type != "resistor" or capacitor.type != "capacitor":
                raise ToleranceAnalysisError("RC tolerance rule must reference a resistor and capacitor.")
            resistance, r_tol = self._component_value(resistor, "value_ohms", "tolerance_fraction")
            capacitance_uf, c_tol = self._component_value(capacitor, "value_uf", "tolerance_fraction")
            required_min, required_max = self._range(rule, "tau_range_ms")
            tau_min = resistance * (1 - r_tol) * capacitance_uf * (1 - c_tol) / 1000
            tau_max = resistance * (1 + r_tol) * capacitance_uf * (1 + c_tol) / 1000
            evidence = {"worst_case_tau_min_ms": round(tau_min, 6), "worst_case_tau_max_ms": round(tau_max, 6),
                        "required_tau_min_ms": required_min, "required_tau_max_ms": required_max,
                        "resistor": resistor.id, "capacitor": capacitor.id,
                        "resistor_tolerance_fraction": r_tol, "capacitor_tolerance_fraction": c_tol}
            if tau_min < required_min or tau_max > required_max:
                return [self._finding("RC_TOLERANCE_OUT_OF_RANGE", "critical", "Worst-case resistor/capacitor tolerance can move RC timing outside its reviewed range.", evidence)]
            return []
        except (KeyError, TypeError, ValueError, CircuitIRError, ToleranceAnalysisError) as error:
            return [self._finding("RC_TOLERANCE_REQUIREMENT_INVALID", "error", str(error), {"requirement": rule})]

    @staticmethod
    def _component_value(component, value_key: str, tolerance_key: str) -> tuple[float, float]:
        try:
            value = float(component.raw[value_key])
            tolerance = float(component.raw[tolerance_key])
        except (KeyError, TypeError, ValueError) as error:
            raise ToleranceAnalysisError(f"{component.id} needs numeric {value_key} and {tolerance_key}.") from error
        if value <= 0 or not 0 <= tolerance < 1:
            raise ToleranceAnalysisError(f"{component.id} value must be positive and tolerance_fraction must be >=0 and <1.")
        return value, tolerance

    @staticmethod
    def _range(rule: dict[str, Any], key: str) -> tuple[float, float]:
        try:
            minimum, maximum = float(rule[key][0]), float(rule[key][1])
        except (KeyError, TypeError, ValueError, IndexError) as error:
            raise ToleranceAnalysisError(f"{key} must be [minimum, maximum].") from error
        if minimum > maximum:
            raise ToleranceAnalysisError(f"{key} is reversed.")
        return minimum, maximum

    @staticmethod
    def _finding(code: str, severity: str, message: str, evidence: dict[str, Any]) -> dict[str, Any]:
        return {"code": code, "severity": severity, "message": message, "evidence": evidence}
