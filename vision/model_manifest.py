"""Validate model artifacts before they can be called production TensorRT."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


class ModelManifestError(ValueError):
    pass


REQUIRED_CAPABILITIES = frozenset({"component_detection", "wire_instance_segmentation", "terminal_localization"})


def validate_manifest_payload(manifest: dict) -> None:
    """Validate manifest claims independently from a particular engine file."""
    required = {"schema_version", "engine_sha256", "target_gpu", "benchmark", "classes", "capabilities"}
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1 or required - set(manifest):
        raise ModelManifestError("Engine manifest is incomplete or has an unsupported schema.")
    if not isinstance(manifest["target_gpu"], str) or not manifest["target_gpu"].strip():
        raise ModelManifestError("Engine manifest must identify the benchmarked GPU.")
    if not isinstance(manifest["classes"], list) or not all(isinstance(item, str) and item for item in manifest["classes"]):
        raise ModelManifestError("Engine manifest must identify its model classes.")
    benchmark = manifest["benchmark"]
    if (not isinstance(benchmark, dict) or not isinstance(benchmark.get("p95_latency_ms"), (int, float))
            or isinstance(benchmark.get("p95_latency_ms"), bool) or benchmark["p95_latency_ms"] <= 0
            or not isinstance(benchmark.get("fault_false_safe_count"), int)
            or isinstance(benchmark.get("fault_false_safe_count"), bool) or benchmark["fault_false_safe_count"] < 0):
        raise ModelManifestError("Engine manifest benchmark values are invalid.")
    if benchmark["p95_latency_ms"] > 150 or benchmark["fault_false_safe_count"] != 0:
        raise ModelManifestError("Engine benchmark does not meet CircuitPulse safety/latency gates.")
    capabilities = manifest["capabilities"]
    if not isinstance(capabilities, list) or not REQUIRED_CAPABILITIES.issubset(set(capabilities)):
        raise ModelManifestError("Engine manifest does not prove the component, wire-segmentation, and terminal-localization capabilities required for automatic graph evidence.")


def validate_engine(engine_path: Path, manifest_path: Path) -> dict:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ModelManifestError(f"Engine manifest unavailable: {error}") from error
    validate_manifest_payload(manifest)
    digest = hashlib.sha256(engine_path.read_bytes()).hexdigest()
    if digest != manifest["engine_sha256"]:
        raise ModelManifestError("Engine checksum does not match its manifest.")
    return manifest
