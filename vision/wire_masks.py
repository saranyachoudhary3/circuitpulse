"""Convert instance-segmentation masks into conservative wire endpoints."""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np


class WireMaskExtractor:
    """Extracts graph endpoints from one binary wire mask.

    A segmentation model supplies masks; this class deliberately refuses masks
    that branch excessively or are too small, since those usually represent a
    crossing/occlusion rather than a single trustworthy jumper wire.
    """

    def extract(self, mask: np.ndarray) -> dict[str, Any]:
        if mask is None or mask.size == 0:
            return {"status": "AMBIGUOUS", "reason": "empty_mask"}
        binary = np.where(mask > 0, 255, 0).astype(np.uint8)
        if cv2.countNonZero(binary) < 12:
            return {"status": "AMBIGUOUS", "reason": "mask_too_small"}
        skeleton = self._skeletonize(binary)
        ys, xs = np.where(skeleton > 0)
        points = list(zip(xs.astype(int), ys.astype(int)))
        if len(points) < 2:
            return {"status": "AMBIGUOUS", "reason": "no_skeleton_path"}
        endpoints, branches = self._topology(points, skeleton)
        if branches > 1 or len(endpoints) != 2:
            return {"status": "AMBIGUOUS", "reason": "branched_or_crossing_wire", "endpoint_count": len(endpoints), "branch_count": branches}
        quality = round(min(1.0, len(points) / 100.0), 3)
        return {"status": "CANDIDATE", "endpoints": [list(endpoints[0]), list(endpoints[1])], "confidence": quality}

    @staticmethod
    def _skeletonize(binary: np.ndarray) -> np.ndarray:
        if hasattr(cv2, "ximgproc") and hasattr(cv2.ximgproc, "thinning"):
            return cv2.ximgproc.thinning(binary)
        skeleton = np.zeros(binary.shape, np.uint8)
        image = binary.copy()
        element = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
        while cv2.countNonZero(image):
            eroded = cv2.erode(image, element)
            opened = cv2.dilate(eroded, element)
            skeleton = cv2.bitwise_or(skeleton, cv2.subtract(image, opened))
            image = eroded
        return skeleton

    @staticmethod
    def _topology(points: list[tuple[int, int]], skeleton: np.ndarray) -> tuple[list[tuple[int, int]], int]:
        endpoints, branches = [], 0
        height, width = skeleton.shape[:2]
        for x, y in points:
            neighbours = 0
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dx == dy == 0:
                        continue
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < width and 0 <= ny < height and skeleton[ny, nx]:
                        neighbours += 1
            if neighbours == 1:
                endpoints.append((x, y))
            elif neighbours > 2:
                branches += 1
        # A slightly thick skeleton may produce endpoint clusters. Keep the two
        # farthest clusters as the physical wire terminals.
        if len(endpoints) > 2:
            first = endpoints[0]
            second = max(endpoints[1:], key=lambda point: (point[0] - first[0]) ** 2 + (point[1] - first[1]) ** 2)
            endpoints = [first, second]
        return endpoints, branches
