"""Create reviewable module-terminal layouts from calibrated pixel clicks."""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np
from vision.calibration import CalibrationState


class LayoutMeasurementError(ValueError):
    """Raised when physical-layout measurement input is incomplete."""


def build_layout_candidate(module: dict[str, Any], pixel_points: list[list[float] | tuple[float, float]], calibration: dict[str, Any]) -> dict[str, Any]:
    """Project ordered terminal clicks into canonical mat millimetres.

    The returned layout deliberately has ``status: candidate``.  A reviewer
    must inspect it against the physical module and change it to ``reviewed``
    in a versioned manifest before automatic terminal mapping will use it.
    """
    if not isinstance(module, dict) or not isinstance(module.get("id"), str):
        raise LayoutMeasurementError("A catalog module is required.")
    pins = module.get("pins")
    if not isinstance(pins, list) or not pins:
        raise LayoutMeasurementError("Module has no ordered pin manifest.")
    if not isinstance(pixel_points, list) or len(pixel_points) != len(pins):
        raise LayoutMeasurementError(f"Expected exactly {len(pins)} terminal points in manifest-pin order.")
    homography = calibration.get("homography") if isinstance(calibration, dict) else None
    marker_ids = calibration.get("marker_ids") if isinstance(calibration, dict) else None
    if not isinstance(homography, list) or not isinstance(marker_ids, list) or set(marker_ids) != {0, 1, 2, 3}:
        raise LayoutMeasurementError("A four-marker calibration result is required.")
    matrix = np.asarray(homography, dtype=np.float64)
    if matrix.shape != (3, 3) or not np.isfinite(matrix).all():
        raise LayoutMeasurementError("Calibration homography must be a finite 3x3 matrix.")
    calibration_id = calibration.get("calibration_id")
    if not isinstance(calibration_id, str):
        frame_size = calibration.get("frame_size")
        if not isinstance(frame_size, list) or len(frame_size) != 2:
            raise LayoutMeasurementError("Calibration result requires calibration_id or frame_size.")
        try:
            calibration_id = CalibrationState(matrix.tolist(), list(marker_ids), (int(frame_size[0]), int(frame_size[1])), 0).calibration_id()
        except (TypeError, ValueError) as error:
            raise LayoutMeasurementError("Calibration frame_size must contain width and height.") from error
    if len(calibration_id) != 64:
        raise LayoutMeasurementError("Calibration calibration_id must be a 64-character hash.")
    try:
        points = np.asarray([[float(point[0]), float(point[1])] for point in pixel_points], dtype=np.float32)
    except (TypeError, ValueError, IndexError) as error:
        raise LayoutMeasurementError("Every terminal point must be [pixel_x, pixel_y].") from error
    if not np.isfinite(points).all():
        raise LayoutMeasurementError("Terminal points must be finite.")
    projected = cv2.perspectiveTransform(points.reshape(-1, 1, 2), matrix).reshape(-1, 2)
    return {
        "status": "candidate",
        "coordinate_system": "calibration_mat_mm",
        "calibration_id": calibration_id,
        "calibration_marker_ids": sorted(marker_ids),
        "measurement_source": "manual_terminal_clicks",
        "terminals": [
            {"pin": pin["name"], "x_mm": round(float(point[0]), 3), "y_mm": round(float(point[1]), 3)}
            for pin, point in zip(pins, projected)
        ],
    }
