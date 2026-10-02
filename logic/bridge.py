"""Safe bridge from calibrated vision endpoints to the live graph actor."""

from __future__ import annotations

from typing import Any

from logic.session import GraphSession
from vision.topology import Terminal, TerminalMapper
from vision.wire_masks import WireMaskExtractor
from vision.calibration import CalibrationMat, CalibrationError


class VisionGraphBridge:
    """Consumes canonical-mm wire endpoints emitted by a segmentation model.

    The bridge does not inspect raw camera pixels. That boundary ensures a
    model must first provide calibrated endpoint positions, after which the
    mapper records all ambiguity instead of silently selecting a nearby pin.
    """

    def __init__(self, mapper: TerminalMapper | None = None):
        self.mapper = mapper or TerminalMapper()
        self.mask_extractor = WireMaskExtractor()

    def observe(self, session: GraphSession, terminals: list[dict[str, Any]], wires: list[dict[str, Any]]) -> dict[str, Any]:
        anchors = [Terminal(item["id"], float(item["x"]), float(item["y"]), float(item.get("radius", 1.0))) for item in terminals]
        candidates, ambiguous = [], []
        for wire in wires:
            endpoints = wire.get("endpoints")
            if not isinstance(endpoints, list) or len(endpoints) != 2:
                ambiguous.append({"status": "AMBIGUOUS", "reason": "wire_has_no_two_endpoints", "wire": wire.get("id")})
                continue
            try:
                start = (float(endpoints[0][0]), float(endpoints[0][1]))
                end = (float(endpoints[1][0]), float(endpoints[1][1]))
            except (TypeError, ValueError, IndexError):
                ambiguous.append({"status": "AMBIGUOUS", "reason": "invalid_endpoint_coordinates", "wire": wire.get("id")})
                continue
            connection = self.mapper.connection(start, end, anchors, wire.get("wire_color"))
            if connection["status"] == "CANDIDATE":
                # Keep model/segmentation quality in the evidence score.  A
                # geometrically perfect endpoint cannot compensate for an
                # uncertain mask classification.
                try:
                    wire_confidence = float(wire.get("confidence", 1.0))
                except (TypeError, ValueError):
                    wire_confidence = 0.0
                connection["confidence"] = round(min(connection["confidence"], max(0.0, min(1.0, wire_confidence))), 3)
                candidates.append({key: connection[key] for key in ("from", "to", "confidence", "wire_color")})
            else:
                ambiguous.append(connection)
        state = session.observe(candidates)
        state["vision_ambiguities"] = ambiguous
        return state

    def observe_masks(self, session: GraphSession, calibration: CalibrationMat, terminals: list[dict[str, Any]], masks: list[dict[str, Any]]) -> dict[str, Any]:
        """Map segmentation masks from pixels into calibrated-mm graph evidence."""
        wires, ambiguous = [], []
        for item in masks:
            result = self.mask_extractor.extract(item.get("mask"))
            if result["status"] != "CANDIDATE":
                ambiguous.append(result | {"wire": item.get("id")})
                continue
            try:
                endpoints = [calibration.project(tuple(point)) for point in result["endpoints"]]
            except CalibrationError as error:
                raise ValueError(str(error)) from error
            wires.append({"id": item.get("id"), "wire_color": item.get("wire_color"), "endpoints": endpoints,
                          "confidence": result["confidence"]})
        state = self.observe(session, terminals, wires)
        state["vision_ambiguities"] = ambiguous + state.get("vision_ambiguities", [])
        return state
