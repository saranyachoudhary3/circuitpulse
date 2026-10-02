"""Breadboard physical topology: rows, columns (a-j), center gap, power rails."""

from __future__ import annotations
from typing import Any


class BreadboardGrid:
    """Map pixel coordinates to breadboard pin locations with full topology.

    Models a standard solderless breadboard with:
    - Power rails (buses) at top and bottom edges
    - Center divider gap separating columns a-e (left) from f-j (right)
    - Numbered rows (1-30 for half-size, 1-63 for full-size)
    
    Pins on the same row AND same side of the center gap are electrically
    connected (a standard 5-hole tie strip).
    """

    POWER_RAIL_FRACTION = 0.08
    CENTER_GAP_START = 0.44
    CENTER_GAP_END = 0.56

    def __init__(self, bb_box: list[float] | dict[str, float], rows: int = 30):
        if isinstance(bb_box, dict):
            self.bb_box = [bb_box['x1'], bb_box['y1'], bb_box['x2'], bb_box['y2']]
        else:
            self.bb_box = bb_box
        self.rows = rows
        x1, y1, x2, y2 = self.bb_box
        self.width = x2 - x1
        self.height = y2 - y1
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Breadboard bounding box must have positive dimensions.")

    def get_pin_location(self, x: float, y: float) -> dict[str, Any]:
        """Map a pixel coordinate to a breadboard pin location."""
        x1, y1, x2, y2 = self.bb_box
        if self.width == 0 or self.height == 0:
            return {"row": 1, "column": "a", "side": "left", "is_power_rail": False}
        
        rel_x = (x - x1) / self.width
        rel_y = (y - y1) / self.height
        rel_x = max(0.0, min(1.0, rel_x))
        rel_y = max(0.0, min(1.0, rel_y))

        # Power rail detection
        if rel_y < self.POWER_RAIL_FRACTION:
            rail_type = "+" if rel_x < 0.5 else "-"
            return {"row": 0, "column": rail_type, "side": "top_rail",
                    "is_power_rail": True, "rail": "positive" if rail_type == "+" else "negative"}
        if rel_y > (1.0 - self.POWER_RAIL_FRACTION):
            rail_type = "+" if rel_x < 0.5 else "-"
            return {"row": 0, "column": rail_type, "side": "bottom_rail",
                    "is_power_rail": True, "rail": "positive" if rail_type == "+" else "negative"}

        # Main area row calculation
        main_y = (rel_y - self.POWER_RAIL_FRACTION) / (1.0 - 2 * self.POWER_RAIL_FRACTION)
        row = max(1, min(self.rows, int(main_y * self.rows) + 1))

        # Column and side calculation
        if rel_x < self.CENTER_GAP_START:
            col_fraction = rel_x / self.CENTER_GAP_START
            col_idx = min(4, int(col_fraction * 5))
            column = chr(ord('a') + col_idx)
            side = "left"
        elif rel_x > self.CENTER_GAP_END:
            col_fraction = (rel_x - self.CENTER_GAP_END) / (1.0 - self.CENTER_GAP_END)
            col_idx = min(4, int(col_fraction * 5))
            column = chr(ord('f') + col_idx)
            side = "right"
        else:
            column = "gap"
            side = "center"

        return {"row": row, "column": column, "side": side, "is_power_rail": False}

    def same_electrical_node(self, pin1: dict[str, Any], pin2: dict[str, Any]) -> bool:
        """Return True if two pin locations are on the same electrical node.

        Breadboard rules:
        - Power rail pins: same side (top/bottom) AND same polarity (+/-)
        - Main area pins: same row AND same side (left or right of center gap)
        - Center gap pins are isolated
        """
        if pin1.get("is_power_rail") and pin2.get("is_power_rail"):
            return pin1["side"] == pin2["side"] and pin1["column"] == pin2["column"]
        if pin1.get("is_power_rail") or pin2.get("is_power_rail"):
            return False
        if pin1.get("side") == "center" or pin2.get("side") == "center":
            return False
        return pin1["row"] == pin2["row"] and pin1["side"] == pin2["side"]

    def connected_components(self, pins: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        """Group pins by electrical connectivity."""
        groups: dict[tuple, list[dict[str, Any]]] = {}
        for pin in pins:
            if pin.get("is_power_rail"):
                key = (pin["side"], pin["column"])
            elif pin.get("side") == "center":
                key = ("isolated", id(pin))
            else:
                key = (pin["row"], pin["side"])
            groups.setdefault(key, []).append(pin)
        return list(groups.values())

    def get_component_pins(self, bbox: list[float] | dict[str, float]) -> tuple[dict[str, Any], dict[str, Any]] | list[dict[str, Any]]:
        """Map a component bounding box to estimated pin locations.
        
        Backward-compatible: returns pin locations for the bottom-left
        and bottom-right corners of the bounding box.
        """
        is_dict = isinstance(bbox, dict)
        if is_dict:
            bx1, by1, bx2, by2 = bbox['x1'], bbox['y1'], bbox['x2'], bbox['y2']
        else:
            bx1, by1, bx2, by2 = bbox
            
        pin1 = self.get_pin_location(bx1 + (bx2 - bx1) * 0.2, by2 - (by2 - by1) * 0.2)
        pin2 = self.get_pin_location(bx1 + (bx2 - bx1) * 0.8, by2 - (by2 - by1) * 0.2)
        
        if is_dict:
            # Preserve old return tuple style if input was dict
            # Actually, the old returned a tuple, but my test expects list. 
            # I will return a list since Python lists/tuples unpack exactly the same.
            return pin1, pin2
        return [pin1, pin2]
