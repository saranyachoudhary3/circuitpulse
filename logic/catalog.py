"""Versioned circuit presets and fiducial-backed component manifests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class CatalogError(ValueError):
    """Raised when a preset or manifest cannot be used safely."""


class ComponentCatalog:
    """Loads reviewed module definitions; unknown modules never gain pin trust."""

    def __init__(self, path: Path | None = None):
        self.path = path or Path(__file__).with_name("manifests") / "catalog.json"
        self._modules = self._load().get("modules", [])
        self._by_fiducial = {item["fiducial_id"]: item for item in self._modules}
        self._by_id = {item["id"]: item for item in self._modules}

    def _load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CatalogError(f"Cannot load component catalog: {error}") from error
        if data.get("schema_version") != 1 or not isinstance(data.get("modules"), list):
            raise CatalogError("Component catalog must use schema_version 1 and contain modules.")
        for module in data["modules"]:
            if not all(isinstance(module.get(key), str) and module[key] for key in ("id", "fiducial_id", "display_name")):
                raise CatalogError("Every manifest needs id, fiducial_id, and display_name.")
            if not isinstance(module.get("pins"), list) or not module["pins"]:
                raise CatalogError(f"Manifest {module['id']} has no reviewed pins.")
        return data

    def get(self, module_id: str) -> dict[str, Any] | None:
        return self._by_id.get(module_id)

    def identify_fiducial(self, fiducial_id: str) -> dict[str, Any] | None:
        return self._by_fiducial.get(fiducial_id)

    @staticmethod
    def terminal_layout_status(module: dict[str, Any]) -> str:
        """Return whether identity can safely become terminal geometry.

        A marker proves a module SKU/orientation, not the exact physical pin
        positions under a particular camera.  Only a measured layout with all
        manifest pins can be used to auto-generate terminal anchors.
        """
        layout = module.get("terminal_layout")
        if not isinstance(layout, dict) or layout.get("status") != "reviewed":
            return "LAYOUT_PENDING_PHYSICAL_MEASUREMENT"
        review = layout.get("review")
        if not isinstance(review, dict) or not all(isinstance(review.get(key), str) and review[key] for key in ("reviewed_by", "reviewed_at", "candidate_sha256")) or len(review.get("candidate_sha256", "")) != 64:
            return "LAYOUT_INVALID"
        if not isinstance(layout.get("calibration_id"), str) or len(layout["calibration_id"]) != 64 or layout.get("coordinate_system") != "calibration_mat_mm":
            return "LAYOUT_INVALID"
        terminals = layout.get("terminals")
        expected = {pin["name"] for pin in module["pins"]}
        if not isinstance(terminals, list) or {item.get("pin") for item in terminals if isinstance(item, dict)} != expected:
            return "LAYOUT_INVALID"
        for terminal in terminals:
            if not all(isinstance(terminal.get(key), (int, float)) for key in ("x_mm", "y_mm")):
                return "LAYOUT_INVALID"
        return "REVIEWED_TERMINAL_LAYOUT"

    def list_public(self) -> list[dict[str, Any]]:
        return [
            {"id": module["id"], "name": module["display_name"], "fiducial_id": module["fiducial_id"],
             "pins": [pin["name"] for pin in module["pins"]], "voltage": module["voltage"],
             "terminal_layout_status": self.terminal_layout_status(module)}
            for module in self._modules
        ]


class PresetCatalog:
    """Loads reviewed graph blueprints used by the authoritative session actor."""

    def __init__(self, directory: Path | None = None):
        self.directory = directory or Path(__file__).with_name("presets")
        self._presets = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        presets: dict[str, dict[str, Any]] = {}
        for path in sorted(self.directory.glob("*.json")):
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise CatalogError(f"Cannot load preset {path.name}: {error}") from error
            self._validate(item, path.name)
            presets[item["id"]] = item
        if not presets:
            raise CatalogError("No circuit presets are installed.")
        return presets

    @staticmethod
    def _validate(item: dict[str, Any], filename: str) -> None:
        if item.get("schema_version") != 1:
            raise CatalogError(f"{filename}: unsupported schema version.")
        if not isinstance(item.get("id"), str) or not isinstance(item.get("connections"), list):
            raise CatalogError(f"{filename}: id and connections are required.")
        seen: set[str] = set()
        for connection in item["connections"]:
            if not all(isinstance(connection.get(key), str) and connection[key] for key in ("id", "from", "to")):
                raise CatalogError(f"{filename}: every connection needs id, from, and to.")
            if connection["id"] in seen:
                raise CatalogError(f"{filename}: duplicate connection {connection['id']}.")
            seen.add(connection["id"])

    def get(self, preset_id: str) -> dict[str, Any]:
        preset = self._presets.get(preset_id)
        if preset is None:
            raise CatalogError(f"Unknown circuit preset: {preset_id}")
        return preset

    def list_public(self) -> list[dict[str, Any]]:
        return [{"id": p["id"], "name": p["name"], "description": p["description"],
                 "required_components": p["required_components"]} for p in self._presets.values()]

    def identify(self, component_types: list[str]) -> list[dict[str, Any]]:
        found = {item.lower().replace("-", "_") for item in component_types}
        ranked = []
        for preset in self._presets.values():
            required = {item.lower().replace("-", "_") for item in preset["required_components"]}
            score = len(required & found) / max(len(required), 1)
            ranked.append({"id": preset["id"], "name": preset["name"], "score": round(score, 3)})
        return sorted(ranked, key=lambda item: item["score"], reverse=True)[:3]
