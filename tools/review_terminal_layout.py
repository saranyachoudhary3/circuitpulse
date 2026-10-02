"""Perform the explicit human review step for measured module terminal geometry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from logic.catalog import ComponentCatalog
from vision.layout_review import LayoutReviewError, review_layout_candidate


def main() -> None:
    parser = argparse.ArgumentParser(description="Review a physically measured CircuitPulse terminal-layout candidate.")
    parser.add_argument("candidate", type=Path, help="Candidate JSON produced by measure_terminal_layout.py")
    parser.add_argument("--reviewer", required=True, help="Named reviewer responsible for comparing geometry to the physical module")
    parser.add_argument("--output", type=Path, required=True, help="Reviewed-layout JSON output for version-control review")
    parser.add_argument("--minimum-spacing-mm", type=float, default=0.25)
    args = parser.parse_args()
    try:
        payload = json.loads(args.candidate.read_text(encoding="utf-8"))
        module_id = payload.get("module_id")
        module = ComponentCatalog().get(module_id)
        if module is None:
            raise LayoutReviewError(f"Candidate names unknown module_id: {module_id!r}")
        layout = review_layout_candidate(module, payload.get("terminal_layout"), args.reviewer, args.minimum_spacing_mm)
    except (OSError, json.JSONDecodeError, LayoutReviewError) as error:
        raise SystemExit(f"LAYOUT_NOT_REVIEWED: {error}") from error
    result = {"schema_version": 1, "module_id": module_id, "terminal_layout": layout}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote reviewed terminal layout to {args.output}. Merge it into the versioned module manifest only after independent review.")


if __name__ == "__main__":
    main()
