"""Minimal safe edit planning from observed topology to a selected blueprint."""

from __future__ import annotations

from typing import Any


def canonical_edge(first: str, second: str) -> str:
    return " <-> ".join(sorted((first, second)))


class RepairPlanner:
    """Rank physical edits deterministically, one action at a time.

    It deliberately plans only explicit graph edits. Component values, power
    ratings, and firmware faults are surfaced separately by typed logic rather
    than being guessed as physical wire moves.
    """

    def plan(self, preset: dict[str, Any], observed: list[dict[str, Any]], findings: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        expected = {canonical_edge(item["from"], item["to"]): item for item in preset.get("connections", [])}
        actual = {canonical_edge(item["from"], item["to"]): item for item in observed
                  if isinstance(item, dict) and isinstance(item.get("from"), str) and isinstance(item.get("to"), str)}
        extra, missing = sorted(set(actual) - set(expected)), sorted(set(expected) - set(actual))
        actions = []
        for edge in extra:
            evidence = actual[edge]
            critical = self._is_power_short(evidence)
            actions.append({"kind": "remove", "priority": 0 if critical else 1, "connection_id": edge,
                            "instruction": f"Remove the wire from {evidence['from']} to {evidence['to']}.",
                            "reason": "It directly joins a positive rail to ground." if critical else "It is not part of the selected blueprint."})
        build_order = {item["id"]: index for index, item in enumerate(preset.get("build_order", []))}
        for edge in missing:
            connection = expected[edge]
            actions.append({"kind": "add", "priority": 10 + build_order.get(connection["id"], len(build_order)), "connection_id": edge,
                            "instruction": f"Connect the {connection.get('wire_color', 'jumper')} wire from {connection['from']} to {connection['to']}.",
                            "reason": connection.get("purpose", "Required selected-blueprint dependency.")})
        for finding in findings or []:
            if finding.get("severity") not in {"critical", "error"}:
                continue
            actions.append({"kind": "electrical_repair", "priority": 2, "code": finding.get("code"),
                            "instruction": finding.get("recommended_action") or "Resolve this deterministic electrical fault and rerun verification.",
                            "reason": finding.get("message", "Deterministic electrical fault.")})
        actions.sort(key=lambda item: (item["priority"], item.get("connection_id", item.get("code", ""))))
        return {"actions": actions, "next_action": actions[0] if actions else None,
                "summary": {"remove": len(extra), "add": len(missing), "total": len(actions)}}

    @staticmethod
    def _is_power_short(edge: dict[str, Any]) -> bool:
        terminals = {edge["from"].lower(), edge["to"].lower()}
        return (any(value.endswith((":5v", ":3v3", ":vcc")) for value in terminals)
                and any(value.endswith((":gnd", ":ground")) for value in terminals))
