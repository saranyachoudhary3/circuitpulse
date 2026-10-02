"""Reviewed steady-state thermal derating checks for components and drivers."""

from __future__ import annotations

from typing import Any


class ThermalAnalysisError(ValueError):
    pass


class ThermalAnalyzer:
    """Use an explicit thermal-resistance model; no package data is guessed."""

    def evaluate(self, rule: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            component_id = rule["component_id"]
            power = float(rule["dissipation_w"])
            ambient = float(rule["ambient_c"])
            theta = float(rule["theta_ja_c_per_w"])
            max_junction = float(rule["max_junction_c"])
            derating = float(rule.get("derating_fraction", 1.0))
            if not isinstance(component_id, str) or not component_id or power < 0 or theta <= 0 or not 0 < derating <= 1:
                raise ValueError
            estimated = ambient + power * theta
            allowable = ambient + (max_junction - ambient) * derating
            evidence = {"component_id": component_id, "dissipation_w": power, "ambient_c": ambient,
                        "theta_ja_c_per_w": theta, "estimated_junction_c": estimated,
                        "max_junction_c": max_junction, "derating_fraction": derating,
                        "derated_junction_limit_c": allowable}
            if estimated > allowable:
                return [self._finding("THERMAL_DERATING_EXCEEDED", "critical", "Estimated steady-state junction temperature exceeds the reviewed derated thermal limit.", evidence)]
            return []
        except (KeyError, TypeError, ValueError):
            return [self._finding("THERMAL_REQUIREMENT_INVALID", "error", "Thermal rule needs named component, non-negative dissipation, ambient, theta_JA, max junction, and 0<derating<=1.", {"requirement": rule})]

    @staticmethod
    def _finding(code: str, severity: str, message: str, evidence: dict[str, Any]) -> dict[str, Any]:
        return {"code": code, "severity": severity, "message": message, "evidence": evidence}
