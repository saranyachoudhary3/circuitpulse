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
                            "instruction": finding.get("recommended_action") or finding.get("message") or "Resolve this deterministic electrical fault and rerun verification.",
                            "reason": finding.get("message", "Deterministic electrical fault.")})
        actions = self._optimize_actions(actions)
        if any(a.get("priority") == 0 for a in actions):
            actions.insert(0, {
                "kind": "safety", "priority": -1,
                "instruction": "Disconnect power (USB cable) before making any changes.",
                "reason": "A direct power short was detected. Remove power to prevent damage.",
            })

        actions.sort(key=lambda item: (item["priority"], item.get("connection_id", item.get("code", ""))))
        
        tutorial_steps = []
        step_idx = 1
        
        if any(a.get("kind") == "safety" for a in actions):
            tutorial_steps.append({
                "step": step_idx,
                "instruction": "Disconnect the USB cable or power supply from your board.",
                "reason": "A direct power short was detected. Remove power to prevent damage.",
                "safety_note": "CRITICAL: Do this before touching any wires."
            })
            step_idx += 1
            
        for a in actions:
            if a.get("kind") == "safety": continue
            
            if a["kind"] == "remove":
                from_t = a["connection_id"].split(" <-> ")[0]
                to_t = a["connection_id"].split(" <-> ")[1]
                tutorial_steps.append({
                    "step": step_idx,
                    "instruction": f"Remove the wire connecting {from_t} to {to_t}",
                    "reason": a.get("reason", "")
                })
                step_idx += 1
            elif a["kind"] == "move":
                tutorial_steps.append({
                    "step": step_idx,
                    "instruction": f"Move the wire end from {a.get('old_end')} to {a.get('new_end')}, keeping it connected at {a.get('fixed')}",
                    "reason": a.get("reason", "")
                })
                step_idx += 1
            elif a["kind"] == "add":
                from_t = a["connection_id"].split(" <-> ")[0]
                to_t = a["connection_id"].split(" <-> ")[1]
                tutorial_steps.append({
                    "step": step_idx,
                    "instruction": f"Connect a wire from {from_t} to {to_t}",
                    "reason": a.get("reason", "")
                })
                step_idx += 1
            elif a["kind"] == "electrical_repair":
                tutorial_steps.append({
                    "step": step_idx,
                    "instruction": a.get("instruction", ""),
                    "reason": a.get("reason", "")
                })
                step_idx += 1
                
        if len(actions) > 0:
            tutorial_steps.append({
                "step": step_idx,
                "instruction": "Reconnect power and verify the circuit",
                "reason": "All planned repair steps are complete."
            })
            
        return {"actions": actions, "next_action": actions[0] if actions else None,
                "summary": {"remove": len(extra), "add": len(missing), "total": len(actions)},
                "tutorial_steps": tutorial_steps}

    def _optimize_actions(self, actions):
        removes = [a for a in actions if a["kind"] == "remove" and a.get("priority") != 0]
        adds = [a for a in actions if a["kind"] == "add"]
        moves = []
        used_removes = set()
        used_adds = set()
        for ri, rem in enumerate(removes):
            rem_parts = set(rem["connection_id"].split(" <-> "))
            for ai, add in enumerate(adds):
                if ai in used_adds:
                    continue
                add_parts = set(add["connection_id"].split(" <-> "))
                shared = rem_parts & add_parts
                if len(shared) == 1:
                    fixed = shared.pop()
                    old_end = (rem_parts - {fixed}).pop()
                    new_end = (add_parts - {fixed}).pop()
                    moves.append({
                        "kind": "move", "priority": rem["priority"],
                        "connection_id": rem["connection_id"],
                        "instruction": f"Move the wire end from {old_end} to {new_end} (keep {fixed} connected).",
                        "reason": f"Wire is in the wrong position.",
                        "old_end": old_end,
                        "new_end": new_end,
                        "fixed": fixed
                    })
                    used_removes.add(ri)
                    used_adds.add(ai)
                    break
        
        remaining = []
        for a in actions:
            if a["kind"] == "remove" and a in removes and removes.index(a) in used_removes:
                continue
            if a["kind"] == "add" and a in adds and adds.index(a) in used_adds:
                continue
            remaining.append(a)
            
        return remaining + moves

    @staticmethod
    def _is_power_short(edge: dict[str, Any]) -> bool:
        import re
        _POSITIVE_PATTERN = re.compile(r'(?i)[:_](v?cc|5v|3v3|3\.3v|vin|vbus|12v|9v|bat\+?|v\+|vdd|vbat|vsys)$')
        _NEGATIVE_PATTERN = re.compile(r'(?i)[:_](g(?:nd|round)|agnd|pgnd|gnd_d|v-|vss|com)$')
        terminals = [edge.get("from", ""), edge.get("to", "")]
        has_positive = any(_POSITIVE_PATTERN.search(t) for t in terminals)
        has_negative = any(_NEGATIVE_PATTERN.search(t) for t in terminals)
        return has_positive and has_negative
