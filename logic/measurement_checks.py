"""Validate measured runtime electrical/protocol behavior against rule packs."""

from __future__ import annotations

from typing import Any

from logic.circuit_ir import CircuitIR


class MeasurementChecks:
    """Checks explicitly supplied instrument/firmware measurements only."""

    def range_check(self, circuit: CircuitIR, rule: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            key = rule["measurement_key"]
            value = float(circuit.measurements["values"][key])
            minimum, maximum = float(rule["min"]), float(rule["max"])
            unit = rule.get("unit", "")
            if not minimum <= value <= maximum:
                return [self._finding("MEASUREMENT_OUT_OF_RANGE", "critical", f"Measured {key}={value} {unit} is outside the reviewed range.",
                                      {"measurement_key": key, "value": value, "min": minimum, "max": maximum, "unit": unit})]
            return []
        except (KeyError, TypeError, ValueError):
            return [self._finding("MEASUREMENT_UNAVAILABLE", "warning", "Required measured value is unavailable or invalid.", {"requirement": rule})]

    def pwm(self, circuit: CircuitIR, rule: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            signal = rule["signal"]
            measured = circuit.measurements["pwm"][signal]
            frequency, duty = float(measured["frequency_hz"]), float(measured["duty_cycle"])
            if not 0 <= duty <= 1 or frequency <= 0:
                raise ValueError
            checks = (("frequency_hz", frequency, float(rule["frequency_min_hz"]), float(rule["frequency_max_hz"])),
                      ("duty_cycle", duty, float(rule["duty_min"]), float(rule["duty_max"])))
            for name, value, minimum, maximum in checks:
                if not minimum <= value <= maximum:
                    return [self._finding("PWM_OUT_OF_RANGE", "critical", f"Measured PWM {name} is outside the reviewed range.",
                                          {"signal": signal, "metric": name, "value": value, "min": minimum, "max": maximum})]
            return []
        except (KeyError, TypeError, ValueError):
            return [self._finding("PWM_MEASUREMENT_UNAVAILABLE", "warning", "Required PWM measurement is unavailable or invalid.", {"requirement": rule})]

    def i2c_ack(self, circuit: CircuitIR, rule: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            address = int(rule["address"], 0) if isinstance(rule["address"], str) else int(rule["address"])
            discovered = circuit.measurements["i2c_addresses"]
            normalized = {int(item, 0) if isinstance(item, str) else int(item) for item in discovered}
            if address not in normalized:
                return [self._finding("I2C_DEVICE_NO_ACK", "error", "Expected I2C device address did not acknowledge.", {"address": hex(address), "discovered": [hex(item) for item in sorted(normalized)]})]
            return []
        except (KeyError, TypeError, ValueError):
            return [self._finding("I2C_SCAN_UNAVAILABLE", "warning", "Required I2C scan measurement is unavailable or invalid.", {"requirement": rule})]

    @staticmethod
    def _finding(code: str, severity: str, message: str, evidence: dict[str, Any]) -> dict[str, Any]:
        return {"code": code, "severity": severity, "message": message, "evidence": evidence}
