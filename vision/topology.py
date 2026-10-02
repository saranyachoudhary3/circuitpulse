"""Terminal attachment with explicit uncertainty, never box-relative pin guesses."""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from typing import Any


@dataclass(frozen=True)
class Terminal:
    id: str
    x: float
    y: float
    radius: float


class TerminalMapper:
    """Associates segmented-wire endpoints with calibrated terminal anchors."""

    def __init__(self, max_distance_mm: float = 3.5, ambiguity_delta_mm: float = 1.0):
        self.max_distance_mm = max_distance_mm
        self.ambiguity_delta_mm = ambiguity_delta_mm

    def attach(self, endpoint: tuple[float, float], terminals: list[Terminal]) -> dict[str, Any]:
        ranked = sorted(((hypot(endpoint[0] - terminal.x, endpoint[1] - terminal.y), terminal) for terminal in terminals), key=lambda item: item[0])
        if not ranked or ranked[0][0] > self.max_distance_mm:
            return {"status": "UNATTACHED", "terminal": None, "confidence": 0.0, "reason": "no_terminal_within_tolerance"}
        nearest_distance, nearest = ranked[0]
        if len(ranked) > 1 and ranked[1][0] - nearest_distance < self.ambiguity_delta_mm:
            return {"status": "AMBIGUOUS", "terminal": nearest.id, "alternatives": [nearest.id, ranked[1][1].id],
                    "confidence": round(max(0.0, 1 - nearest_distance / self.max_distance_mm), 3), "reason": "multiple_terminals_near_endpoint"}
        return {"status": "ATTACHED", "terminal": nearest.id,
                "confidence": round(max(0.0, 1 - nearest_distance / self.max_distance_mm), 3), "reason": "calibrated_terminal_match"}

    def connection(self, start: tuple[float, float], end: tuple[float, float], terminals: list[Terminal], wire_color: str | None = None) -> dict[str, Any]:
        first, second = self.attach(start, terminals), self.attach(end, terminals)
        if first["status"] != "ATTACHED" or second["status"] != "ATTACHED":
            return {"status": "AMBIGUOUS", "endpoints": [first, second], "wire_color": wire_color}
        return {"status": "CANDIDATE", "from": first["terminal"], "to": second["terminal"],
                "confidence": round(min(first["confidence"], second["confidence"]), 3), "wire_color": wire_color,
                "evidence_mode": "vision"}
