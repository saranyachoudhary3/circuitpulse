"""Electrical envelopes for reviewed modules and discrete component safety."""

from __future__ import annotations

import json
import os
from typing import Any

from logic.catalog import ComponentCatalog


class DigitalTwinEngine:
    """Rejects unsafe declared operating envelopes before hardware is powered.

    This intentionally evaluates provided measurements/ratings only. It does
    not estimate current or voltage from an image.
    """

    def __init__(self, catalog: ComponentCatalog | None = None):
        self.catalog = catalog or ComponentCatalog()
        self.MAX_CURRENT_MA = {}
        self.NEEDS_FLYBACK = set()
        self.specs = {}
        
        specs_path = os.path.join(os.path.dirname(__file__), "manifests", "component_specs.json")
        try:
            with open(specs_path, "r") as f:
                data = json.load(f)
                self.specs = data.get("components", {})
                for comp_id, spec in self.specs.items():
                    if "total_max_current_ma" in spec:
                        self.MAX_CURRENT_MA[comp_id] = spec["total_max_current_ma"]
                    if spec.get("needs_flyback"):
                        self.NEEDS_FLYBACK.add(comp_id)
        except Exception:
            pass

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
        
        spec = self.specs.get(module_id) if isinstance(module_id, str) else None

        if manifest is None and spec is None:
            return [self._finding("UNKNOWN_COMPONENT", "warning", "Component has no reviewed digital twin; electrical verification is withheld.", component)]
            
        display_name = manifest.get('display_name') if manifest else spec.get('display_name')
        findings = []
        supplied = component.get("supply_voltage")
        if supplied is not None:
            voltage = self._voltage_label(supplied)
            if voltage is None:
                findings.append(self._finding("INVALID_SUPPLY_VALUE", "error", "Supply voltage must be a numeric value.", component))
            else:
                valid_voltage = False
                
                # Check continuous range if spec is available
                if spec:
                    v_min, v_max = spec.get("input_voltage_range_v", [spec.get("operating_voltage_v", 0.0), spec.get("operating_voltage_v", 0.0)])
                    if v_min <= voltage <= v_max:
                        valid_voltage = True
                
                # Check discrete bucket if manifest is available and spec didn't pass
                if not valid_voltage and manifest and "voltage" in manifest:
                    label = "3V3" if (3.0 <= voltage <= 3.6) else ("5V" if (4.75 <= voltage <= 5.25) else None)
                    if label in manifest["voltage"]:
                        valid_voltage = True
                        
                if not valid_voltage:
                    findings.append(self._finding("VOLTAGE_INCOMPATIBLE", "critical", f"{display_name} is not approved for {supplied}V.", component))
        else:
            findings.append(self._finding("SUPPLY_UNMEASURED", "warning", f"{display_name} has no measured/declared supply voltage.", component))
            
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
    def _voltage_label(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _finding(code: str, severity: str, message: str, component: dict[str, Any]) -> dict[str, Any]:
        return {"code": code, "severity": severity, "message": message, "evidence": {"component_id": component.get("id"), "module_id": component.get("module_id")}}
