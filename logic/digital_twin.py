"""Electrical envelopes for reviewed modules and discrete component safety."""

from __future__ import annotations

from typing import Any

from logic.catalog import ComponentCatalog


class DigitalTwinEngine:
    """Rejects unsafe declared operating envelopes before hardware is powered.

    This intentionally evaluates provided measurements/ratings only. It does
    not estimate current or voltage from an image.
    """

    MAX_CURRENT_MA = {"sg90_servo": 700, "relay_1ch": 80, "motor_driver": 2000, "rc522": 30}
    NEEDS_FLYBACK = {"relay_1ch", "motor_driver"}

    def __init__(self, catalog: ComponentCatalog | None = None):
        self.catalog = catalog or ComponentCatalog()

    def evaluate(self, components: list[dict[str, Any]]) -> dict[str, Any]:
        if not isinstance(components, list):
            raise ValueError("components must be a list.")
        findings = []
        for component in components:
            findings.extend(self._evaluate_component(component))
        status = "FAIL" if any(item["severity"] in {"critical", "error"} for item in findings) else ("INDETERMINATE" if findings else "PASS")
        return {"status": status, "findings": findings, "checked_components": len(components), "evidence_mode": "declared_operating_envelope"}

    def _evaluate_component(self, component: dict[str, Any]) -> list[dict[str, Any]]:
        module_id = component.get("module_id")
        manifest = self.catalog.get(module_id) if isinstance(module_id, str) else None
        if manifest is None:
            return [self._finding("UNKNOWN_COMPONENT", "warning", "Component has no reviewed digital twin; electrical verification is withheld.", component)]
        findings = []
        supplied = component.get("supply_voltage")
        if supplied is not None:
            label = self._voltage_label(supplied)
            if label is None:
                findings.append(self._finding("INVALID_SUPPLY_VALUE", "error", "Supply voltage must be a numeric 3.3 or 5 volt value.", component))
            elif label not in manifest["voltage"]:
                findings.append(self._finding("VOLTAGE_INCOMPATIBLE", "critical", f"{manifest['display_name']} is not approved for {label}.", component))
        else:
            findings.append(self._finding("SUPPLY_UNMEASURED", "warning", f"{manifest['display_name']} has no measured/declared supply voltage.", component))
        maximum = self.MAX_CURRENT_MA.get(module_id)
        load = component.get("load_current_ma")
        if maximum is not None and load is not None:
            try:
                if float(load) > maximum:
                    findings.append(self._finding("CURRENT_LIMIT_EXCEEDED", "critical", f"Declared load current exceeds the reviewed {maximum} mA limit.", component))
            except (TypeError, ValueError):
                findings.append(self._finding("INVALID_CURRENT_VALUE", "error", "load_current_ma must be numeric.", component))
        if module_id in self.NEEDS_FLYBACK and component.get("external_inductive_load") and not component.get("flyback_protection"):
            findings.append(self._finding("FLYBACK_PROTECTION_MISSING", "critical", "Inductive load requires declared flyback protection.", component))
        return findings

    @staticmethod
    def _voltage_label(value: Any) -> str | None:
        try:
            voltage = float(value)
        except (TypeError, ValueError):
            return None
        if 3.0 <= voltage <= 3.6:
            return "3V3"
        if 4.75 <= voltage <= 5.25:
            return "5V"
        return None

    @staticmethod
    def _finding(code: str, severity: str, message: str, component: dict[str, Any]) -> dict[str, Any]:
        return {"code": code, "severity": severity, "message": message, "evidence": {"component_id": component.get("id"), "module_id": component.get("module_id")}}
