"""Instrument evidence contracts for future analyzers, meters, and probes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol


class InstrumentAdapter(Protocol):
    name: str
    def sample(self) -> list[dict[str, Any]]: ...


class InstrumentRegistry:
    """Normalizes optional instrument readings without making hardware mandatory."""

    ALLOWED_KINDS = {"continuity", "voltage", "current", "logic", "serial"}

    def __init__(self):
        self._adapters: dict[str, InstrumentAdapter] = {}

    def register(self, adapter: InstrumentAdapter) -> None:
        if not getattr(adapter, "name", ""):
            raise ValueError("Instrument adapter needs a name.")
        self._adapters[adapter.name] = adapter

    def collect(self) -> list[dict[str, Any]]:
        readings = []
        for adapter in self._adapters.values():
            for reading in adapter.sample():
                readings.append(self.normalize(reading, adapter.name))
        return readings

    def normalize(self, reading: dict[str, Any], adapter: str = "manual") -> dict[str, Any]:
        if not isinstance(reading, dict) or reading.get("kind") not in self.ALLOWED_KINDS:
            raise ValueError("Instrument reading needs a supported kind.")
        if reading["kind"] == "continuity":
            if not all(isinstance(reading.get(key), str) and reading[key] for key in ("from", "to")):
                raise ValueError("Continuity evidence needs from and to terminals.")
            if not isinstance(reading.get("connected"), bool):
                raise ValueError("Continuity evidence needs an explicit boolean connected result.")
        normalized = dict(reading)
        normalized.update({"source": "instrumented", "adapter": adapter,
                           "timestamp": datetime.now(timezone.utc).isoformat(), "confidence": 1.0})
        return normalized
