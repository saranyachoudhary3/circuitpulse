"""Import timestamped logic-analyzer CSV captures into CircuitPulse evidence."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


class TraceImportError(ValueError):
    pass


MAX_TRACE_ROWS = 200_000
TIME_COLUMNS = ("time_s", "time", "timestamp_s")


def import_logic_csv(path: Path, signal_nets: dict[str, str]) -> dict[str, Any]:
    """Convert a simple Saleae-style sampled CSV into ``digital_trace``.

    ``signal_nets`` explicitly maps CSV headers to reviewed circuit net names.
    Columns are never inferred: an unrecognised capture column has no effect
    on circuit logic, and a requested column must be present in every sample.
    """
    if not isinstance(signal_nets, dict) or not signal_nets or not all(isinstance(header, str) and header and isinstance(net, str) and net for header, net in signal_nets.items()):
        raise TraceImportError("signal_nets must map non-empty CSV headers to reviewed non-empty net names.")
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            if not reader.fieldnames:
                raise TraceImportError("Logic CSV has no header row.")
            time_column = next((name for name in TIME_COLUMNS if name in reader.fieldnames), None)
            if time_column is None:
                raise TraceImportError(f"Logic CSV requires one time column: {TIME_COLUMNS}.")
            missing = sorted(set(signal_nets) - set(reader.fieldnames))
            if missing:
                raise TraceImportError(f"Logic CSV is missing requested signal columns: {missing}")
            events, previous_time = [], -1.0
            for index, row in enumerate(reader, start=2):
                if index > MAX_TRACE_ROWS + 1:
                    raise TraceImportError(f"Logic CSV exceeds the {MAX_TRACE_ROWS} sample safety limit.")
                try:
                    time_us = float(row[time_column]) * 1_000_000
                except (TypeError, ValueError) as error:
                    raise TraceImportError(f"CSV row {index} has invalid {time_column}.") from error
                if time_us < 0 or time_us < previous_time:
                    raise TraceImportError(f"CSV row {index} time is negative or out of order.")
                levels = {}
                for header, net in signal_nets.items():
                    level = _logic_level(row.get(header))
                    if level is None:
                        raise TraceImportError(f"CSV row {index} signal {header!r} is not a supported logic level.")
                    levels[net] = level
                events.append({"time_us": time_us, "levels": levels})
                previous_time = time_us
    except OSError as error:
        raise TraceImportError(f"Cannot read logic CSV: {error}") from error
    if not events:
        raise TraceImportError("Logic CSV contains no samples.")
    return {
        "schema_version": 1,
        "evidence_type": "logic_analyzer_csv",
        "source_file": path.name,
        "sample_count": len(events),
        "measurements": {"digital_trace": events},
    }


def import_voltage_csv(path: Path, channel_nets: dict[str, str]) -> dict[str, Any]:
    """Convert timestamped voltage CSV capture to reviewed-net voltage evidence."""
    if not isinstance(channel_nets, dict) or not channel_nets or not all(isinstance(header, str) and header and isinstance(net, str) and net for header, net in channel_nets.items()):
        raise TraceImportError("channel_nets must map non-empty CSV headers to reviewed non-empty net names.")
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            if not reader.fieldnames:
                raise TraceImportError("Voltage CSV has no header row.")
            time_column = next((name for name in TIME_COLUMNS if name in reader.fieldnames), None)
            if time_column is None:
                raise TraceImportError(f"Voltage CSV requires one time column: {TIME_COLUMNS}.")
            missing = sorted(set(channel_nets) - set(reader.fieldnames))
            if missing:
                raise TraceImportError(f"Voltage CSV is missing requested channel columns: {missing}")
            events, previous_time = [], -1.0
            for index, row in enumerate(reader, start=2):
                if index > MAX_TRACE_ROWS + 1:
                    raise TraceImportError(f"Voltage CSV exceeds the {MAX_TRACE_ROWS} sample safety limit.")
                try:
                    time_us = float(row[time_column]) * 1_000_000
                except (TypeError, ValueError) as error:
                    raise TraceImportError(f"CSV row {index} has invalid {time_column}.") from error
                if time_us < 0 or time_us < previous_time:
                    raise TraceImportError(f"CSV row {index} time is negative or out of order.")
                voltages = {}
                for header, net in channel_nets.items():
                    try:
                        voltages[net] = float(row[header])
                    except (KeyError, TypeError, ValueError) as error:
                        raise TraceImportError(f"CSV row {index} channel {header!r} is not numeric.") from error
                events.append({"time_us": time_us, "voltages_v": voltages})
                previous_time = time_us
    except OSError as error:
        raise TraceImportError(f"Cannot read voltage CSV: {error}") from error
    if not events:
        raise TraceImportError("Voltage CSV contains no samples.")
    return {"schema_version": 1, "evidence_type": "voltage_trace_csv", "source_file": path.name,
            "sample_count": len(events), "measurements": {"voltage_trace": events}}


def _logic_level(value: Any) -> int | None:
    normalized = str(value).strip().lower()
    if normalized in {"0", "false", "low", "l"}:
        return 0
    if normalized in {"1", "true", "high", "h"}:
        return 1
    return None
