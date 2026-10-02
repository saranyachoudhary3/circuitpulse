"""Generate print-ready ArUco markers for the fixed calibration mat and modules."""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2

from vision.fiducials import MODULE_MARKER_IDS


def save_marker(dictionary, marker_id: int, output: Path, pixels: int) -> None:
    image = cv2.aruco.generateImageMarker(dictionary, marker_id, pixels)
    if not cv2.imwrite(str(output), image):
        raise RuntimeError(f"Could not write {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate CircuitPulse ArUco marker PNGs.")
    parser.add_argument("--output", default="artifacts/fiducials", help="Output directory")
    parser.add_argument("--pixels", type=int, default=600, help="Marker edge length in pixels")
    args = parser.parse_args()
    if not hasattr(cv2, "aruco"):
        raise SystemExit("opencv-contrib-python-headless is required for ArUco generation.")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    for marker_id in range(4):
        save_marker(dictionary, marker_id, output / f"calibration_{marker_id}.png", args.pixels)
    for marker_id, label in MODULE_MARKER_IDS.items():
        save_marker(dictionary, marker_id, output / f"{marker_id}_{label}.png", args.pixels)
    print(f"Generated {4 + len(MODULE_MARKER_IDS)} markers in {output}")


if __name__ == "__main__":
    main()
