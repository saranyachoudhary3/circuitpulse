"""Validate a CircuitPulse capture/label manifest before training or release use."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from logic.dataset_manifest import DatasetManifestError, load_and_validate, summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate CircuitPulse session-disjoint training data.")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--require-preset", action="append", default=[], help="Preset ID required in the dataset; repeat as needed")
    args = parser.parse_args()
    try:
        payload = load_and_validate(args.manifest, required_presets=set(args.require_preset))
        print(json.dumps(summary(payload), indent=2))
    except DatasetManifestError as error:
        raise SystemExit(f"DATASET_NOT_READY: {error}") from error


if __name__ == "__main__":
    main()
