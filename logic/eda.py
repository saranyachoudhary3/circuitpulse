"""Safe import of simple SPICE and KiCad legacy netlists into graph evidence."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any


class EdaImportError(ValueError):
    pass


KICAD_NODE = re.compile(r"\(node\s+\(ref\s+\"([^\"]+)\"\)\s+\(pin\s+\"([^\"]+)\"\)\)")


def import_kicad_legacy_netlist(text: str) -> dict[str, Any]:
    """Import KiCad's textual legacy net blocks into a normalized graph."""
    if not isinstance(text, str) or not text.strip():
        raise EdaImportError("KiCad netlist text is required.")
    nets = []
    for body in _balanced_net_blocks(text):
        name_match = re.search(r"\(name\s+\"([^\"]+)\"\)", body)
        if not name_match:
            continue
        name = name_match.group(1)
        terminals = [f"{ref}:{pin}" for ref, pin in KICAD_NODE.findall(body)]
        if terminals:
            nets.append({"name": name, "terminals": terminals})
    if not nets:
        raise EdaImportError("No KiCad legacy net entries were found.")
    return {"format": "kicad_legacy", "nets": nets, "connections": _net_connections(nets)}


def import_spice_netlist(text: str) -> dict[str, Any]:
    """Import passive two-terminal SPICE records as net connectivity.

    This deliberately ignores models/directives rather than fabricating a pin
    map for unsupported devices.
    """
    if not isinstance(text, str) or not text.strip():
        raise EdaImportError("SPICE netlist text is required.")
    nets: dict[str, list[str]] = defaultdict(list)
    components = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("*", ".")):
            continue
        tokens = line.split()
        if len(tokens) < 3 or tokens[0][0].upper() not in {"R", "C", "L", "D", "V", "I"}:
            continue
        component, first, second = tokens[:3]
        terminals = [f"{component}:1", f"{component}:2"]
        nets[first].append(terminals[0])
        nets[second].append(terminals[1])
        components.append({"id": component, "type": component[0].upper(), "pins": {"1": first, "2": second}})
    if not components:
        raise EdaImportError("No supported two-terminal SPICE components were found.")
    normalized_nets = [{"name": name, "terminals": terminals} for name, terminals in nets.items()]
    return {"format": "spice", "components": components, "nets": normalized_nets, "connections": _net_connections(normalized_nets)}


def _net_connections(nets: list[dict[str, Any]]) -> list[dict[str, str]]:
    connections = []
    for net in nets:
        terminals = net["terminals"]
        for terminal in terminals[1:]:
            connections.append({"from": terminals[0], "to": terminal, "net": net["name"]})
    return connections


def _balanced_net_blocks(text: str) -> list[str]:
    """Extract nested ``(net ...)`` S-expressions without a fragile regex."""
    blocks = []
    position = 0
    while True:
        start = text.find("(net", position)
        if start < 0:
            return blocks
        depth, index = 0, start
        while index < len(text):
            if text[index] == "(":
                depth += 1
            elif text[index] == ")":
                depth -= 1
                if depth == 0:
                    blocks.append(text[start:index + 1])
                    position = index + 1
                    break
            index += 1
        else:
            raise EdaImportError("Unbalanced parentheses in KiCad netlist.")
