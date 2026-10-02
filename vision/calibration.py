"""Calibration-mat support for stable, canonical circuit coordinates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any

import cv2
import numpy as np


class CalibrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class CalibrationState:
    homography: list[list[float]]
    marker_ids: list[int]
    frame_size: tuple[int, int]
    reprojection_error: float
    calibrated_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"homography": self.homography, "marker_ids": self.marker_ids,
                "frame_size": list(self.frame_size), "reprojection_error": self.reprojection_error,
                "calibration_id": self.calibration_id(), "calibrated_at": self.calibrated_at}

    def calibration_id(self) -> str:
        """Stable ID binding vision evidence to this exact camera transform."""
        content = {"homography": self.homography, "marker_ids": self.marker_ids, "frame_size": list(self.frame_size)}
        return sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


class CalibrationMat:
    """Finds four mat markers and maps their inner corners to board coordinates.

    Marker IDs must be 0, 1, 2, 3 arranged top-left, top-right, bottom-right,
    bottom-left. The target coordinate system is millimetres on the printed mat.
    """

    REQUIRED_IDS = (0, 1, 2, 3)

    def __init__(self, width_mm: float = 240.0, height_mm: float = 180.0):
        self.width_mm = width_mm
        self.height_mm = height_mm
        self.state: CalibrationState | None = None

    def calibrate(self, frame: np.ndarray) -> CalibrationState:
        if not hasattr(cv2, "aruco"):
            raise CalibrationError("OpenCV ArUco support is unavailable; install opencv-contrib-python.")
        if frame is None or frame.size == 0:
            raise CalibrationError("Cannot calibrate from an empty frame.")
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        detector = cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters())
        corners, ids, _ = detector.detectMarkers(gray)
        if ids is None:
            raise CalibrationError("Calibration mat markers were not found.")
        lookup = {int(marker_id): marker.reshape(4, 2) for marker, marker_id in zip(corners, ids.flatten())}
        missing = [marker_id for marker_id in self.REQUIRED_IDS if marker_id not in lookup]
        if missing:
            raise CalibrationError(f"Calibration mat is missing marker IDs: {missing}")
        src = np.float32([lookup[0].mean(axis=0), lookup[1].mean(axis=0), lookup[2].mean(axis=0), lookup[3].mean(axis=0)])
        dst = np.float32([[0, 0], [self.width_mm, 0], [self.width_mm, self.height_mm], [0, self.height_mm]])
        homography, _ = cv2.findHomography(src, dst, cv2.RANSAC)
        if homography is None:
            raise CalibrationError("Could not calculate a stable calibration homography.")
        projected = cv2.perspectiveTransform(src.reshape(-1, 1, 2), homography).reshape(-1, 2)
        error = float(np.mean(np.linalg.norm(projected - dst, axis=1)))
        height, width = frame.shape[:2]
        self.state = CalibrationState(homography.tolist(), list(self.REQUIRED_IDS), (width, height), round(error, 4),
                                      datetime.now(timezone.utc).isoformat())
        return self.state

    def health(self, frame_size: tuple[int, int] | None, max_reprojection_error_mm: float = 1.0) -> dict[str, Any]:
        """State whether this calibration can safely support automatic mapping."""
        if self.state is None:
            return {"status": "BLOCKED", "reason": "Calibration has not been completed."}
        if self.state.reprojection_error > max_reprojection_error_mm:
            return {"status": "BLOCKED", "reason": f"Calibration reprojection error exceeds {max_reprojection_error_mm} mm."}
        if frame_size is not None and tuple(frame_size) != self.state.frame_size:
            return {"status": "BLOCKED", "reason": "Active camera resolution differs from calibration frame size."}
        return {"status": "READY", "calibration_id": self.state.calibration_id(), "calibrated_at": self.state.calibrated_at,
                "reprojection_error_mm": self.state.reprojection_error}

    def project(self, point: tuple[float, float]) -> tuple[float, float]:
        if self.state is None:
            raise CalibrationError("Calibration has not been completed.")
        matrix = np.asarray(self.state.homography, dtype=np.float64)
        result = cv2.perspectiveTransform(np.float32([[point]]), matrix)[0][0]
        return float(result[0]), float(result[1])
