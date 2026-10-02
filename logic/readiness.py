"""Pre-demo release/readiness gates for automatic CircuitPulse verification."""

from __future__ import annotations

from typing import Any

from logic.catalog import ComponentCatalog, PresetCatalog


class ReadinessError(ValueError):
    pass


def automatic_verification_readiness(*, camera_connected: bool, model_verified: bool,
                                    model_artifact_id: str | None, calibration_health: dict[str, Any],
                                    components: ComponentCatalog, presets: PresetCatalog,
                                    preset_id: str | None = None) -> dict[str, Any]:
    """Return blocking reasons before automatic graph evidence may be enabled."""
    blockers: list[dict[str, str]] = []
    if not camera_connected:
        blockers.append(_blocker("CAMERA_UNAVAILABLE", "Camera feed is unavailable."))
    if not model_verified or not model_artifact_id:
        blockers.append(_blocker("MODEL_UNVERIFIED", "No benchmarked TensorRT model artifact is active."))
    if calibration_health.get("status") != "READY":
        blockers.append(_blocker("CALIBRATION_UNREADY", calibration_health.get("reason", "Calibration is unavailable.")))
    selected: dict[str, Any] | None = None
    if preset_id is not None:
        selected = presets.get(preset_id)
        for module_id in selected.get("required_components", []):
            module = components.get(module_id)
            if module is not None and components.terminal_layout_status(module) != "REVIEWED_TERMINAL_LAYOUT":
                blockers.append(_blocker("TERMINAL_LAYOUT_UNREVIEWED", f"{module['display_name']} lacks reviewed physical terminal geometry."))
    return {"status": "READY" if not blockers else "BLOCKED", "automatic_verification": not blockers,
            "preset": {"id": selected["id"], "name": selected["name"]} if selected else None,
            "blockers": blockers, "calibration": calibration_health}


def _blocker(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}
