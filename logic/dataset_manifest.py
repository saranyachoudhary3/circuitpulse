"""Safety gates for reproducible vision datasets used by CircuitPulse."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any


class DatasetManifestError(ValueError):
    pass


REQUIRED_ANNOTATIONS = frozenset({
    "components", "module_ids", "terminal_polygons", "breadboard_rows_rails",
    "wire_masks", "wire_endpoints", "wire_colors", "resistor_values", "polarity", "faults",
})
REQUIRED_SPLITS = frozenset({"train", "validation", "test"})


def load_and_validate(path: Path, required_presets: set[str] | None = None,
                      verify_artifacts: bool = True) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DatasetManifestError(f"Cannot load dataset manifest: {error}") from error
    validate(payload, required_presets=required_presets,
             artifact_root=path.parent if verify_artifacts else None)
    return payload


def validate(payload: dict[str, Any], required_presets: set[str] | None = None,
             artifact_root: Path | None = None) -> None:
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise DatasetManifestError("Dataset manifest must use schema_version 1.")
    if not isinstance(payload.get("dataset_id"), str) or not payload["dataset_id"].strip():
        raise DatasetManifestError("Dataset manifest requires a non-empty dataset_id.")
    profile = payload.get("capture_profile")
    if not isinstance(profile, dict):
        raise DatasetManifestError("Dataset manifest requires a capture_profile.")
    missing_profile = {"camera_id", "resolution", "fps", "calibration_mat_id", "lighting_profile"} - set(profile)
    if missing_profile or any(not profile[key] for key in set(profile) - {"fps"}) or not isinstance(profile.get("fps"), (int, float)) or profile["fps"] <= 0:
        raise DatasetManifestError("Capture profile is incomplete; fixed camera, mat, and lighting must be identified.")
    annotations = payload.get("annotation_coverage")
    if not isinstance(annotations, list) or not REQUIRED_ANNOTATIONS.issubset(set(annotations)):
        missing = sorted(REQUIRED_ANNOTATIONS - set(annotations or []))
        raise DatasetManifestError(f"Dataset annotation coverage is incomplete: {missing}")
    counts = payload.get("annotation_counts")
    if not isinstance(counts, dict) or any(not isinstance(counts.get(label), int) or counts[label] <= 0
                                           for label in REQUIRED_ANNOTATIONS):
        raise DatasetManifestError("Dataset annotation_counts must report a positive reviewed count for every required label type.")
    presets = payload.get("supported_presets")
    if not isinstance(presets, list) or not all(isinstance(item, str) and item for item in presets):
        raise DatasetManifestError("Dataset manifest requires supported_presets.")
    if required_presets and not required_presets.issubset(set(presets)):
        raise DatasetManifestError(f"Dataset omits supported presets: {sorted(required_presets - set(presets))}")
    splits = payload.get("splits")
    if not isinstance(splits, dict) or REQUIRED_SPLITS - set(splits):
        raise DatasetManifestError("Dataset manifest requires train, validation, and test splits.")
    sessions_seen: dict[str, str] = {}
    sample_ids: set[str] = set()
    for split in REQUIRED_SPLITS:
        records = splits[split]
        if not isinstance(records, list) or not records:
            raise DatasetManifestError(f"Dataset split '{split}' must contain at least one captured sample.")
        for record in records:
            if not isinstance(record, dict):
                raise DatasetManifestError(f"Dataset split '{split}' has an invalid sample record.")
            sample_id, session_id = record.get("sample_id"), record.get("assembly_session_id")
            if not isinstance(sample_id, str) or not sample_id or not isinstance(session_id, str) or not session_id:
                raise DatasetManifestError("Every dataset sample needs sample_id and assembly_session_id.")
            if sample_id.lower().startswith("replace-") or session_id.lower().startswith("replace-"):
                raise DatasetManifestError("Placeholder sample/session identifiers cannot be used as release dataset evidence.")
            if sample_id in sample_ids:
                raise DatasetManifestError(f"Duplicate sample_id: {sample_id}")
            sample_ids.add(sample_id)
            prior_split = sessions_seen.setdefault(session_id, split)
            if prior_split != split:
                raise DatasetManifestError(f"Assembly session '{session_id}' leaks from {prior_split} into {split}.")
            _validate_artifact_record(record, artifact_root)


def _validate_artifact_record(record: dict[str, Any], artifact_root: Path | None) -> None:
    required = ("frame_path", "annotation_path", "frame_sha256", "annotation_sha256")
    if any(not isinstance(record.get(key), str) or not record[key] for key in required):
        raise DatasetManifestError("Every dataset sample needs frame/annotation paths and SHA-256 evidence.")
    for path_key, digest_key in (("frame_path", "frame_sha256"), ("annotation_path", "annotation_sha256")):
        digest = record[digest_key]
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest.lower()):
            raise DatasetManifestError(f"Sample {record['sample_id']} has an invalid {digest_key}.")
        if artifact_root is None:
            continue
        candidate = (artifact_root / record[path_key]).resolve()
        root = artifact_root.resolve()
        try:
            candidate.relative_to(root)
        except ValueError as error:
            raise DatasetManifestError(f"Sample {record['sample_id']} artifact path escapes the dataset directory.") from error
        if not candidate.is_file():
            raise DatasetManifestError(f"Sample {record['sample_id']} artifact is missing: {record[path_key]}")
        actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
        if actual != digest:
            raise DatasetManifestError(f"Sample {record['sample_id']} {path_key} checksum does not match the manifest.")


def summary(payload: dict[str, Any]) -> dict[str, Any]:
    """Produce an auditable compact summary after validation."""
    validate(payload)
    return {
        "dataset_id": payload["dataset_id"],
        "capture_profile": payload["capture_profile"],
        "supported_presets": payload["supported_presets"],
        "split_sample_counts": {name: len(records) for name, records in payload["splits"].items()},
        "ready_for_training": True,
    }
