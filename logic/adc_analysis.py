"""Deterministic ADC reference, input-range, and captured-code validation."""

from __future__ import annotations

from typing import Any

from logic.circuit_ir import CircuitIR


class ADCAnalysisError(ValueError):
    pass


class ADCAnalyzer:
    """Check explicit ADC facts; no voltage is inferred from image color or labels."""

    def evaluate(self, circuit: CircuitIR, rule: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            channel = rule["channel"]
            if not isinstance(channel, str) or not channel:
                raise ADCAnalysisError("ADC channel must be a non-empty string.")
            reference = float(rule["reference_voltage_v"])
            input_min, input_max = self._range(rule, "input_voltage_range_v")
            if reference <= 0 or input_min < 0 or input_min > input_max:
                raise ADCAnalysisError("ADC reference must be positive and input range must be ordered/non-negative.")
            findings = []
            if input_max > reference:
                findings.append(self._finding("ADC_INPUT_OVERVOLTAGE", "critical", "Declared analog input can exceed the ADC reference voltage.",
                                              {"channel": channel, "input_max_v": input_max, "reference_voltage_v": reference}))
            resolution = rule.get("resolution_bits")
            if resolution is not None:
                resolution = int(resolution)
                if not 1 <= resolution <= 32:
                    raise ADCAnalysisError("ADC resolution_bits must be from 1 to 32.")
                raw = circuit.measurements.get("adc", {}).get(channel)
                if raw is None:
                    findings.append(self._finding("ADC_MEASUREMENT_UNAVAILABLE", "warning", "No captured ADC code is available for the reviewed channel.", {"channel": channel}))
                else:
                    raw = int(raw)
                    maximum_code = (1 << resolution) - 1
                    if not 0 <= raw <= maximum_code:
                        findings.append(self._finding("ADC_CODE_INVALID", "error", "Captured ADC code is outside the configured resolution range.",
                                                      {"channel": channel, "raw_code": raw, "max_code": maximum_code}))
                    else:
                        voltage = reference * raw / maximum_code
                        expected = rule.get("expected_voltage_range_v")
                        if expected is not None:
                            expected_min, expected_max = self._range(rule, "expected_voltage_range_v")
                            if not expected_min <= voltage <= expected_max:
                                findings.append(self._finding("ADC_MEASUREMENT_OUT_OF_RANGE", "error", "Captured ADC code converts outside the reviewed expected voltage range.",
                                                              {"channel": channel, "raw_code": raw, "derived_voltage_v": round(voltage, 6),
                                                               "expected_min_v": expected_min, "expected_max_v": expected_max}))
            return findings
        except (KeyError, TypeError, ValueError, ADCAnalysisError) as error:
            return [self._finding("ADC_REQUIREMENT_INVALID", "error", str(error), {"requirement": rule})]

    @staticmethod
    def _range(rule: dict[str, Any], key: str) -> tuple[float, float]:
        try:
            minimum, maximum = float(rule[key][0]), float(rule[key][1])
        except (KeyError, TypeError, ValueError, IndexError) as error:
            raise ADCAnalysisError(f"{key} must be [minimum, maximum].") from error
        if minimum > maximum:
            raise ADCAnalysisError(f"{key} is reversed.")
        return minimum, maximum

    @staticmethod
    def _finding(code: str, severity: str, message: str, evidence: dict[str, Any]) -> dict[str, Any]:
        return {"code": code, "severity": severity, "message": message, "evidence": evidence}
