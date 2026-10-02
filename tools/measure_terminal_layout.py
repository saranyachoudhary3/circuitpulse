"""Generate a candidate module terminal layout from calibrated terminal clicks.

Example:
    python tools/measure_terminal_layout.py --module-id arduino_uno \
      --calibration artifacts/calibration.json --points artifacts/uno_points.json

``points`` is a JSON list of [x, y] image-pixel clicks in the exact pin order
returned by ``GET /api/modules``. Candidate layouts are intentionally not
written into the reviewed catalog automatically.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Executing a file under tools/ makes that directory Python's import root.
# Add the repository root so this documented direct command works on Windows,
# Linux, and macOS without requiring package installation first.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logic.catalog import ComponentCatalog
from vision.layout_measurement import LayoutMeasurementError, build_layout_candidate


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a reviewable CircuitPulse terminal-layout candidate.")
    parser.add_argument("--module-id", required=True, help="Reviewed catalog module ID")
    parser.add_argument("--calibration", required=True, help="Calibration JSON returned by /api/calibration")
    parser.add_argument("--points", required=True, help="JSON file containing ordered [pixel_x, pixel_y] clicks")
    parser.add_argument("--output", help="Candidate layout output; defaults under artifacts/layouts")
    args = parser.parse_args()
    catalog = ComponentCatalog()
    module = catalog.get(args.module_id)
    if module is None:
        raise SystemExit(f"Unknown module ID: {args.module_id}")
    try:
        calibration_data = json.loads(Path(args.calibration).read_text(encoding="utf-8"))
        calibration = calibration_data.get("calibration", calibration_data)
        points = json.loads(Path(args.points).read_text(encoding="utf-8"))
        layout = build_layout_candidate(module, points, calibration)
    except (OSError, json.JSONDecodeError, LayoutMeasurementError) as error:
        raise SystemExit(f"Could not create candidate layout: {error}") from error
    output = Path(args.output) if args.output else Path("artifacts") / "layouts" / f"{args.module_id}.candidate.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"module_id": module["id"], "terminal_layout": layout}, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote candidate layout for {module['display_name']} to {output}. Review it before adding status: reviewed to the catalog.")


if __name__ == "__main__":
    main()
