"""Trust boundary for trained-model output before it reaches the graph actor."""

from __future__ import annotations

from typing import Any

from logic.catalog import ComponentCatalog
from vision.calibration import CalibrationState


class VisionEvidenceError(ValueError):
    """Raised when automatic vision evidence is not safe to consume."""


class VisionEvidenceValidator:
    """Validate provenance, calibration, module layout, and endpoint payloads.

    This validator is deliberately stricter than the low-level bridge.  The
    bridge is useful for unit tests and offline replay; automatic production
    evidence must identify the benchmarked model artifact and the exact active
    calibration, and must originate from reviewed physical terminal geometry.
    """

    CONTRACT_VERSION = 1

    def __init__(self, catalog: ComponentCatalog):
        self.catalog = catalog

    def validate(self, payload: dict[str, Any], calibration: CalibrationState | None,
                 model_verified: bool, model_artifact_id: str | None) -> dict[str, list[dict[str, Any]]]:
        if not isinstance(payload, dict) or payload.get("contract_version") != self.CONTRACT_VERSION:
            raise VisionEvidenceError("Automatic vision evidence requires contract_version 1.")
        if calibration is None:
            raise VisionEvidenceError("Automatic vision evidence requires an active calibration.")
        if not model_verified or not model_artifact_id:
            raise VisionEvidenceError("Automatic graph updates require a benchmarked TensorRT model artifact.")
        if payload.get("model_artifact_id") != model_artifact_id:
            raise VisionEvidenceError("Vision evidence was produced by a different or unverified model artifact.")
        if payload.get("calibration_id") != calibration.calibration_id():
            raise VisionEvidenceError("Vision evidence does not match the active calibration.")
        terminals = self._terminals(payload.get("terminals"))
        wires = self._wires(payload.get("wires"))
        return {"terminals": terminals, "wires": wires}

    def _terminals(self, terminals: Any) -> list[dict[str, Any]]:
        if not isinstance(terminals, list) or not terminals:
            raise VisionEvidenceError("Automatic evidence needs a non-empty terminal list.")
        validated, ids = [], set()
        for terminal in terminals:
            if not isinstance(terminal, dict):
                raise VisionEvidenceError("Every terminal must be an object.")
            identifier, module_id, pin = terminal.get("id"), terminal.get("module_id"), terminal.get("pin")
            if not all(isinstance(value, str) and value for value in (identifier, module_id, pin)):
                raise VisionEvidenceError("Every terminal needs id, module_id, and pin.")
            if identifier in ids:
                raise VisionEvidenceError(f"Duplicate terminal id: {identifier}")
            module = self.catalog.get(module_id)
            if module is None:
                raise VisionEvidenceError(f"Unknown module in terminal evidence: {module_id}")
            if self.catalog.terminal_layout_status(module) != "REVIEWED_TERMINAL_LAYOUT":
                raise VisionEvidenceError(f"Module {module_id} has no reviewed terminal geometry.")
            if pin not in {item["name"] for item in module["pins"]}:
                raise VisionEvidenceError(f"Pin {pin} is not in reviewed manifest {module_id}.")
            try:
                x, y = float(terminal["x"]), float(terminal["y"])
                radius = float(terminal.get("radius", 1.0))
            except (KeyError, TypeError, ValueError) as error:
                raise VisionEvidenceError(f"Terminal {identifier} has invalid canonical coordinates.") from error
            if radius <= 0:
                raise VisionEvidenceError(f"Terminal {identifier} has invalid radius.")
            ids.add(identifier)
            validated.append({"id": identifier, "x": x, "y": y, "radius": radius})
        return validated

    @staticmethod
    def _wires(wires: Any) -> list[dict[str, Any]]:
        if not isinstance(wires, list):
            raise VisionEvidenceError("Automatic evidence needs a wires list.")
        validated = []
        for wire in wires:
            if not isinstance(wire, dict) or not isinstance(wire.get("id"), str):
                raise VisionEvidenceError("Every wire needs a string id.")
            endpoints = wire.get("endpoints")
            if not isinstance(endpoints, list) or len(endpoints) != 2:
                raise VisionEvidenceError(f"Wire {wire['id']} needs exactly two endpoints.")
            try:
                normalized_endpoints = [[float(point[0]), float(point[1])] for point in endpoints]
                confidence = float(wire.get("confidence", 0))
            except (TypeError, ValueError, IndexError) as error:
                raise VisionEvidenceError(f"Wire {wire['id']} has invalid endpoint/confidence data.") from error
            if not 0 <= confidence <= 1:
                raise VisionEvidenceError(f"Wire {wire['id']} confidence must be between 0 and 1.")
            validated.append({"id": wire["id"], "endpoints": normalized_endpoints, "confidence": confidence,
                              "wire_color": wire.get("wire_color")})
        return validated
