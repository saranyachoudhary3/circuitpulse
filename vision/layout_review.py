"""Review and provenance-bind measured terminal geometry before production use."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from math import hypot
from typing import Any


class LayoutReviewError(ValueError):
    pass


def review_layout_candidate(module: dict[str, Any], candidate: dict[str, Any], reviewer: str,
                            minimum_spacing_mm: float = 0.25,
                            reviewed_at: str | None = None) -> dict[str, Any]:
    """Return a reviewed layout only after structural and provenance checks.

    This is intentionally an explicit human-release action. The returned
    object can be placed in a version-controlled module manifest; candidate
    geometry can never elevate itself to automatic production evidence.
    """
    if not isinstance(module, dict) or not isinstance(module.get("id"), str):
        raise LayoutReviewError("A known module manifest is required.")
    if not isinstance(candidate, dict) or candidate.get("status") != "candidate":
        raise LayoutReviewError("Only a terminal-layout candidate may be reviewed.")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise LayoutReviewError("A non-empty reviewer identity is required.")
    if not isinstance(minimum_spacing_mm, (int, float)) or minimum_spacing_mm <= 0:
        raise LayoutReviewError("minimum_spacing_mm must be positive.")
    if candidate.get("coordinate_system") != "calibration_mat_mm":
        raise LayoutReviewError("Candidate geometry must use calibration_mat_mm coordinates.")
    calibration_id = candidate.get("calibration_id")
    if not isinstance(calibration_id, str) or len(calibration_id) != 64:
        raise LayoutReviewError("Candidate must be bound to a 64-character calibration_id.")
    expected = [pin["name"] for pin in module.get("pins", []) if isinstance(pin, dict) and isinstance(pin.get("name"), str)]
    terminals = candidate.get("terminals")
    if not isinstance(terminals, list) or len(terminals) != len(expected):
        raise LayoutReviewError("Candidate terminal count does not match the module manifest.")
    received = [item.get("pin") for item in terminals if isinstance(item, dict)]
    if received != expected:
        raise LayoutReviewError("Candidate terminal pins must match the manifest pins in manifest order.")
    normalized = []
    for terminal in terminals:
        try:
            x, y = float(terminal["x_mm"]), float(terminal["y_mm"])
        except (KeyError, TypeError, ValueError) as error:
            raise LayoutReviewError("Every candidate terminal needs numeric x_mm and y_mm.") from error
        normalized.append({"pin": terminal["pin"], "x_mm": round(x, 3), "y_mm": round(y, 3)})
    for index, first in enumerate(normalized):
        for second in normalized[index + 1:]:
            if hypot(first["x_mm"] - second["x_mm"], first["y_mm"] - second["y_mm"]) < minimum_spacing_mm:
                raise LayoutReviewError(f"Candidate terminals {first['pin']} and {second['pin']} are closer than {minimum_spacing_mm} mm.")
    canonical_candidate = json.dumps(candidate, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "status": "reviewed",
        "coordinate_system": "calibration_mat_mm",
        "calibration_id": calibration_id,
        "terminals": normalized,
        "review": {
            "reviewed_by": reviewer.strip(),
            "reviewed_at": reviewed_at or datetime.now(timezone.utc).isoformat(),
            "candidate_sha256": hashlib.sha256(canonical_candidate).hexdigest(),
            "minimum_spacing_mm": minimum_spacing_mm,
        },
    }
