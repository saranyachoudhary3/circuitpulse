"""Create a validated TensorRT engine manifest from measured release results."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from vision.model_manifest import REQUIRED_CAPABILITIES, ModelManifestError, validate_manifest_payload


def build_manifest(engine: Path, target_gpu: str, p95_latency_ms: float,
                   fault_false_safe_count: int, classes: list[str], capabilities: list[str]) -> dict:
    """Build release metadata only when its claims meet the safety contract."""
    if not engine.is_file():
        raise ModelManifestError(f"Engine does not exist: {engine}")
    manifest = {
        "schema_version": 1,
        "engine_sha256": hashlib.sha256(engine.read_bytes()).hexdigest(),
        "target_gpu": target_gpu,
        "classes": classes,
        "capabilities": capabilities,
        "benchmark": {"p95_latency_ms": p95_latency_ms, "fault_false_safe_count": fault_false_safe_count},
    }
    validate_manifest_payload(manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Write CircuitPulse TensorRT release metadata.")
    parser.add_argument("engine", type=Path, help="Built TensorRT .engine artifact")
    parser.add_argument("--target-gpu", required=True, help="Exact GPU used for benchmark")
    parser.add_argument("--p95-latency-ms", type=float, required=True, help="Measured p95 end-to-end model latency")
    parser.add_argument("--fault-false-safe-count", type=int, required=True, help="Held-out fault fixtures incorrectly marked safe")
    parser.add_argument("--classes", required=True, nargs="+", help="Model class names")
    parser.add_argument("--capabilities", required=True, nargs="+",
                        help="Verified engine capabilities; required: " + ", ".join(sorted(REQUIRED_CAPABILITIES)))
    args = parser.parse_args()
    try:
        manifest = build_manifest(args.engine, args.target_gpu, args.p95_latency_ms,
                                  args.fault_false_safe_count, args.classes, args.capabilities)
    except ModelManifestError as error:
        raise SystemExit(str(error)) from error
    destination = args.engine.with_suffix(".manifest.json")
    destination.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {destination}")


if __name__ == "__main__":
    main()
