"""Replay golden sessions and calculate safety-first release metrics."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

from logic.catalog import PresetCatalog
from logic.netlist import NetlistError, NetlistVerifier
from logic.logic_engine import CircuitLogicEngine
from logic.circuit_ir import CircuitIRError
from logic.session import GraphSession


class BenchmarkError(ValueError):
    pass


MIN_FAULT_FIXTURES_PER_PRESET = 10
MIN_DISTINCT_FAULT_CLASSES_PER_PRESET = 8
MAX_VISUAL_P95_MS = 150
MIN_GRAPH_UPDATES_PER_SECOND = 15
MAX_STABLE_UPDATE_MS = 500


def replay_fixture(path: Path, presets: PresetCatalog | None = None) -> dict[str, Any]:
    try:
        fixture = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BenchmarkError(f"Cannot load fixture: {error}") from error
    catalog = presets or PresetCatalog()
    session = GraphSession(catalog.get(fixture["preset_id"]))
    for frame in fixture.get("frames", []):
        session.observe(frame.get("connections", []))
    for confirmation in fixture.get("confirmations", []):
        session.confirm(confirmation["from"], confirmation["to"], confirmation["accepted"], confirmation.get("wire_color"))
    if "netlist" in fixture:
        try:
            report = CircuitLogicEngine().analyze(fixture["netlist"])
        except (NetlistError, CircuitIRError) as error:
            raise BenchmarkError(f"Invalid netlist in {path.name}: {error}") from error
        state = session.state()
        session.attach_deterministic_verification(report, state["graph_revision"], state["graph_fingerprint"],
                                                  fixture.get("terminal_nets"), fixture["netlist"])
    evidence = _fixture_evidence(fixture, path)
    state = session.state()
    expected = fixture.get("expected_status")
    return {"fixture": path.name, "preset_id": fixture["preset_id"], "expected_status": expected, "actual_status": state["status"], "evidence": evidence,
            "passed": state["status"] == expected, "false_safe": expected == "FAULT" and state["status"] == "PASS"}


def _fixture_evidence(fixture: dict[str, Any], fixture_path: Path) -> dict[str, str]:
    """Classify benchmark provenance; absent metadata is development-only."""
    evidence = fixture.get("evidence")
    if evidence is None:
        return {"class": "development_synthetic"}
    if not isinstance(evidence, dict) or evidence.get("class") not in {"development_synthetic", "held_out_physical"}:
        raise BenchmarkError(f"Fixture {fixture_path.name} has invalid evidence class.")
    if evidence["class"] == "held_out_physical":
        required = ("capture_session_id", "capture_sha256", "capture_path", "operator")
        if not all(isinstance(evidence.get(key), str) and evidence[key] for key in required) or len(evidence["capture_sha256"]) != 64:
            raise BenchmarkError(f"Physical fixture {fixture_path.name} requires capture_session_id, operator, capture_path, and 64-character capture_sha256.")
        capture = (fixture_path.parent / evidence["capture_path"]).resolve()
        try:
            capture.relative_to(fixture_path.parent.resolve())
        except ValueError as error:
            raise BenchmarkError(f"Physical fixture {fixture_path.name} capture_path escapes its fixture directory.") from error
        if not capture.is_file():
            raise BenchmarkError(f"Physical fixture {fixture_path.name} capture artifact is missing: {evidence['capture_path']}")
        if hashlib.sha256(capture.read_bytes()).hexdigest() != evidence["capture_sha256"]:
            raise BenchmarkError(f"Physical fixture {fixture_path.name} capture SHA-256 does not match its artifact.")
        if fixture.get("expected_status") == "FAULT" and (not isinstance(fixture.get("fault_class"), str) or not fixture["fault_class"].strip()):
            raise BenchmarkError(f"Physical fault fixture {fixture_path.name} requires a non-empty fault_class.")
    return dict(evidence)


def replay_suite(directory: Path, measurements_path: Path | None = None) -> dict[str, Any]:
    fixtures = [replay_fixture(path) for path in sorted(directory.glob("*.json"))]
    if not fixtures:
        raise BenchmarkError("No benchmark fixtures found.")
    false_safe = sum(item["false_safe"] for item in fixtures)
    passed = sum(item["passed"] for item in fixtures)
    catalog = PresetCatalog()
    coverage = _coverage(fixtures, catalog)
    measurements = _load_measurements(measurements_path or directory.parent / "release_measurements.json")
    operational = _operational_gates(measurements)
    development_ready = false_safe == 0 and passed == len(fixtures)
    return {"fixtures": fixtures, "total": len(fixtures), "passed": passed,
            "accuracy": round(passed / len(fixtures), 3), "false_safe_count": false_safe,
            "development_ready": development_ready, "coverage": coverage, "operational_gates": operational,
            "release_ready": development_ready and coverage["ready"] and operational["ready"]}


def _coverage(fixtures: list[dict[str, Any]], catalog: PresetCatalog) -> dict[str, Any]:
    by_preset: dict[str, dict[str, Any]] = {preset["id"]: {"positive": 0, "fault": 0, "development_positive": 0, "development_fault": 0, "fault_classes": set()} for preset in catalog.list_public()}
    for fixture in fixtures:
        counts = by_preset.get(fixture.get("preset_id"))
        if counts is None:
            continue
        held_out = fixture.get("evidence", {}).get("class") == "held_out_physical"
        if fixture.get("expected_status") == "FAULT":
            counts["fault" if held_out else "development_fault"] += 1
            if held_out:
                counts["fault_classes"].add(fixture.get("fault_class"))
        elif fixture.get("expected_status") == "PASS":
            counts["positive" if held_out else "development_positive"] += 1
    missing = [preset_id for preset_id, counts in by_preset.items()
               if counts["positive"] < 1 or counts["fault"] < MIN_FAULT_FIXTURES_PER_PRESET
               or len(counts["fault_classes"]) < MIN_DISTINCT_FAULT_CLASSES_PER_PRESET]
    public_counts = {preset_id: {**counts, "fault_classes": sorted(item for item in counts["fault_classes"] if item)} for preset_id, counts in by_preset.items()}
    return {"ready": not missing, "evidence_requirement": "held_out_physical", "required_fault_fixtures_per_preset": MIN_FAULT_FIXTURES_PER_PRESET,
            "required_distinct_fault_classes_per_preset": MIN_DISTINCT_FAULT_CLASSES_PER_PRESET,
            "by_preset": public_counts, "missing_presets": missing}


def _load_measurements(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BenchmarkError(f"Invalid release measurements: {error}") from error
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise BenchmarkError("Release measurements must use schema_version 1.")
    return data


def _operational_gates(measurements: dict[str, Any] | None) -> dict[str, Any]:
    if measurements is None:
        return {"ready": False, "reason": "Measured release metrics are unavailable."}
    required = ("circuit_verdict_accuracy", "endpoint_accuracy_confirmed", "endpoint_accuracy_automatic",
                "stable_update_ms", "visual_p95_latency_ms", "graph_updates_per_second",
                "continuous_rehearsal_minutes", "network_disabled_clean_boot", "false_electrical_pass_count")
    missing = [key for key in required if key not in measurements]
    if missing:
        return {"ready": False, "reason": f"Missing measured release metrics: {missing}"}
    passed = (measurements["circuit_verdict_accuracy"] >= 0.95
              and measurements["endpoint_accuracy_confirmed"] >= 0.95
              and measurements["endpoint_accuracy_automatic"] >= 0.90
              and measurements["stable_update_ms"] <= MAX_STABLE_UPDATE_MS
              and measurements["visual_p95_latency_ms"] <= MAX_VISUAL_P95_MS
              and measurements["graph_updates_per_second"] >= MIN_GRAPH_UPDATES_PER_SECOND
              and measurements["continuous_rehearsal_minutes"] >= 30
              and measurements["network_disabled_clean_boot"] is True
              and measurements["false_electrical_pass_count"] == 0)
    return {"ready": bool(passed), "measurements": measurements}
