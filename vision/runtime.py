"""Validated model selection for laptop TensorRT and development fallbacks."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from vision.model_manifest import ModelManifestError, validate_engine


@dataclass(frozen=True)
class ModelSelection:
    path: str
    backend: str
    verified: bool
    reason: str
    artifact_id: str | None = None


def choose_model(project_root: Path) -> ModelSelection:
    """Prefer a GPU-specific TensorRT engine, never silently download a model.

    A TensorRT engine is hardware/version specific and must be generated and
    benchmarked on the presentation laptop. Until that artifact exists, the
    checked-in PyTorch model is an explicitly labelled development fallback.
    """
    configured = os.environ.get("CIRCUITPULSE_MODEL_PATH")
    if configured:
        candidate = Path(configured)
        if candidate.is_file():
            if candidate.suffix == ".engine":
                try:
                    manifest = validate_engine(candidate, candidate.with_suffix(".manifest.json"))
                    return ModelSelection(str(candidate), "TensorRT", True, f"configured validated TensorRT engine for {manifest['target_gpu']}", manifest["engine_sha256"])
                except ModelManifestError as error:
                    raise FileNotFoundError(f"Configured TensorRT engine rejected: {error}") from error
            return ModelSelection(str(candidate), "PyTorch", False, "configured local development model")
    engine = project_root / "models" / "circuitpulse_fp16.engine"
    if engine.is_file():
        try:
            manifest = validate_engine(engine, engine.with_suffix(".manifest.json"))
            return ModelSelection(str(engine), "TensorRT", True, f"validated TensorRT engine for {manifest['target_gpu']}", manifest["engine_sha256"])
        except ModelManifestError as error:
            engine_reason = f"TensorRT engine rejected: {error}"
    else:
        engine_reason = "TensorRT engine unavailable"
    # Prefer the v3 unified model trained on Merged-Dataset (8 classes, 70.9% test mAP@50).
    v3_model = project_root / "trained_models" / "circuitpulse_v3_merged_best.pt"
    if v3_model.is_file():
        return ModelSelection(str(v3_model), "PyTorch", False, f"{engine_reason}; using v3 merged development model (8 classes)")
    model = project_root / "runs" / "detect" / "ProductionRun" / "circuit_master_optimized" / "weights" / "best.pt"
    if model.is_file():
        return ModelSelection(str(model), "PyTorch", False, f"{engine_reason}; using legacy development fallback")
    fallback = project_root / "yolov8n.pt"
    if fallback.is_file():
        return ModelSelection(str(fallback), "PyTorch", False, "production model unavailable; using generic fallback")
    raise FileNotFoundError("No local CircuitPulse model was found. Set CIRCUITPULSE_MODEL_PATH to a validated local model.")
