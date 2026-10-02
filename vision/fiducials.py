"""ArUco module identification backed by the reviewed component catalog."""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from logic.catalog import ComponentCatalog


# Print these numeric IDs using DICT_4X4_50 and place the indicated catalog
# label beside the marker. IDs 0-3 remain reserved for the calibration mat.
MODULE_MARKER_IDS = {
    10: "CP-UNO-R3", 11: "CP-NANO-V3", 12: "CP-ESP32-DEVKIT", 13: "CP-DHT",
    14: "CP-HCSR04", 15: "CP-HCSR501", 16: "CP-SOIL", 17: "CP-FLAME",
    18: "CP-I2C-SENSOR", 19: "CP-OLED", 20: "CP-SG90", 21: "CP-RELAY-1CH",
    22: "CP-MOTOR-DRV", 23: "CP-RC522",
}


class ModuleFiducialDetector:
    """Maps visible marker IDs to reviewed module manifests, or explicit unknowns."""

    def __init__(self, catalog: ComponentCatalog):
        self.catalog = catalog

    def detect(self, frame: np.ndarray) -> list[dict[str, Any]]:
        if not hasattr(cv2, "aruco"):
            return [{"status": "UNAVAILABLE", "reason": "OpenCV ArUco support is unavailable"}]
        if frame is None or frame.size == 0:
            return []
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        detector = cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters())
        corners, ids, _ = detector.detectMarkers(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
        if ids is None:
            return []
        found = []
        for marker_corners, marker_id in zip(corners, ids.flatten()):
            numeric_id = int(marker_id)
            manifest_id = MODULE_MARKER_IDS.get(numeric_id)
            manifest = self.catalog.identify_fiducial(manifest_id) if manifest_id else None
            points = marker_corners.reshape(4, 2)
            bbox = {"x1": int(points[:, 0].min()), "y1": int(points[:, 1].min()),
                    "x2": int(points[:, 0].max()), "y2": int(points[:, 1].max())}
            if manifest is None:
                found.append({"marker_id": numeric_id, "status": "UNKNOWN_MODULE", "bbox": bbox,
                              "reason": "Marker is not associated with a reviewed module manifest."})
            else:
                layout_status = self.catalog.terminal_layout_status(manifest)
                found.append({"marker_id": numeric_id, "status": "REVIEWED_MODULE" if layout_status == "REVIEWED_TERMINAL_LAYOUT" else "IDENTITY_ONLY",
                              "module_id": manifest["id"], "display_name": manifest["display_name"],
                              "pins": [pin["name"] for pin in manifest["pins"]], "voltage": manifest["voltage"],
                              "terminal_layout_status": layout_status,
                              "reason": None if layout_status == "REVIEWED_TERMINAL_LAYOUT" else "Module identity is known, but measured terminal geometry is not installed."})
        return found
