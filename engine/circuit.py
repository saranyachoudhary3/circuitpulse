import os
import json
import time

CIRCUITS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "circuits")

BOARD_MIN_CONF = 0.40
WIRE_MIN_CONF = 0.18
PROXIMITY_MARGIN = 75
LED_RESISTOR_MARGIN = 160

MCU_MAP = {
    "arduino_uno": "ATmega328P (Arduino Uno)",
    "arduino_nano": "ATmega328P (Arduino Nano)",
    "arduino_mega": "ATmega2560 (Arduino Mega)",
    "esp32": "ESP32 Dual-Core (240MHz)",
    "esp8266": "ESP8266 (80MHz)",
}

FUNCTIONAL_CLASSES = {
    "led", "resistor", "capacitor", "transistor",
    "button", "switch", "diode", "relay",
    "lm358", "ic", "crystal_oscillator", "ultrasonic",
    "motor", "servo", "buzzer", "sensor", "potentiometer",
}

POWER_CLASSES = {
    "esp32", "esp8266", "battery", "power_module",
    "lipo", "power_supply", "dc_power_port", "arduino",
}


class CircuitEngine:
    def __init__(self):
        self.circuits = {}
        self.load_circuit_presets()
        self.last_valid_board_time = 0
        self.locked_circuit_id = "none"
        self.locked_circuit_name = "Scanning..."
        self.locked_mcu_name = ""

    def load_circuit_presets(self):
        if not os.path.exists(CIRCUITS_DIR):
            return
        for fname in os.listdir(CIRCUITS_DIR):
            if fname.endswith(".json"):
                path = os.path.join(CIRCUITS_DIR, fname)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        cid = data.get("id", os.path.splitext(fname)[0])
                        self.circuits[cid] = data
                except Exception:
                    pass

    def list_circuits(self):
        return [
            {"id": cid, "name": d.get("name", cid), "description": d.get("description", "")}
            for cid, d in self.circuits.items()
        ]

    def _boxes_are_connected(self, b1, b2, margin=PROXIMITY_MARGIN):
        ex1 = b1["x1"] - margin
        ey1 = b1["y1"] - margin
        ex2 = b1["x2"] + margin
        ey2 = b1["y2"] + margin
        return not (b2["x2"] < ex1 or b2["x1"] > ex2 or b2["y2"] < ey1 or b2["y1"] > ey2)

    def _describe_location(self, bbox, fw, fh):
        cx = (bbox["x1"] + bbox["x2"]) / 2.0
        cy = (bbox["y1"] + bbox["y2"]) / 2.0
        col = "left" if cx < fw * 0.35 else ("right" if cx > fw * 0.65 else "center")
        row = "top" if cy < fh * 0.35 else ("bottom" if cy > fh * 0.65 else "middle")
        if row == "middle" and col == "center":
            return "center of frame"
        if row == "middle":
            return col + " side"
        if col == "center":
            return row + " center"
        return row + "-" + col

    def _resolve_arduino_pin(self, pt, arduino_box):
        x, y = pt
        bx1, by1 = arduino_box["x1"], arduino_box["y1"]
        bx2, by2 = arduino_box["x2"], arduino_box["y2"]
        bw = bx2 - bx1
        bh = by2 - by1
        if bw <= 0 or bh <= 0:
            return "arduino:unknown"
        rel_x = (x - bx1) / float(bw)
        rel_y = (y - by1) / float(bh)
        if rel_y < 0.45:
            if rel_x < 0.22:
                return "arduino:pin15"
            elif rel_x < 0.33:
                return "arduino:D13"
            elif rel_x < 0.43:
                return "arduino:D12"
            elif rel_x < 0.53:
                return "arduino:D11"
            elif rel_x < 0.63:
                return "arduino:D8"
            elif rel_x < 0.77:
                return "arduino:pin7"
            elif rel_x < 0.88:
                return "arduino:D4"
            else:
                return "arduino:D0"
        elif rel_y > 0.55:
            if rel_x < 0.25:
                return "arduino:5V"
            elif rel_x < 0.45:
                return "arduino:GND"
            elif rel_x < 0.65:
                return "arduino:pin17"
            else:
                return "arduino:A0"
        return "arduino:center"

    def _resolve_breadboard_row(self, pt, breadboard_box):
        x, y = pt
        bx1, by1 = breadboard_box["x1"], breadboard_box["y1"]
        bx2, by2 = breadboard_box["x2"], breadboard_box["y2"]
        bw = bx2 - bx1
        bh = by2 - by1
        if bw <= 0 or bh <= 0:
            return 1
        rel = (x - bx1) / float(bw) if bw > bh else (y - by1) / float(bh)
        return max(1, min(30, int(round(rel * 29)) + 1))

    def _merge_collinear_wires(self, wire_boxes):
        if len(wire_boxes) <= 1:
            return wire_boxes

        merged = []
        used = set()

        for i in range(len(wire_boxes)):
            if i in used:
                continue
            b1 = wire_boxes[i]["bbox"]
            cur_box = dict(b1)
            cur_conf = wire_boxes[i]["confidence"]

            for j in range(i + 1, len(wire_boxes)):
                if j in used:
                    continue
                b2 = wire_boxes[j]["bbox"]

                # Check if b1 and b2 are close endpoints of the same wire
                dist_x = min(abs(b1["x1"] - b2["x2"]), abs(b1["x2"] - b2["x1"]))
                dist_y = min(abs(b1["y1"] - b2["y2"]), abs(b1["y2"] - b2["y1"]))

                # Overlap or nearby ends
                if dist_x < 45 and dist_y < 45:
                    cur_box["x1"] = min(cur_box["x1"], b2["x1"])
                    cur_box["y1"] = min(cur_box["y1"], b2["y1"])
                    cur_box["x2"] = max(cur_box["x2"], b2["x2"])
                    cur_box["y2"] = max(cur_box["y2"], b2["y2"])
                    cur_conf = max(cur_conf, wire_boxes[j]["confidence"])
                    used.add(j)

            used.add(i)
            merged.append({
                "class": "wire",
                "confidence": cur_conf,
                "bbox": cur_box
            })

        return merged

    def _analyze_wire_topology(self, wire_boxes, non_wire_component_boxes):
        topology = []
        for wire in wire_boxes:
            wb = wire["bbox"]
            ep1 = {"x1": wb["x1"] - 16, "y1": wb["y1"] - 16, "x2": wb["x1"] + 16, "y2": wb["y1"] + 16}
            ep2 = {"x1": wb["x2"] - 16, "y1": wb["y2"] - 16, "x2": wb["x2"] + 16, "y2": wb["y2"] + 16}
            comp_start = next((c for c in non_wire_component_boxes if self._boxes_are_connected(ep1, c["bbox"], PROXIMITY_MARGIN)), None)
            comp_end = next((c for c in non_wire_component_boxes if self._boxes_are_connected(ep2, c["bbox"], PROXIMITY_MARGIN)), None)
            floating = comp_start is None and comp_end is None
            dangling = bool(comp_start) != bool(comp_end)
            topology.append({
                "wire": wire,
                "start_comp": comp_start,
                "end_comp": comp_end,
                "floating": floating,
                "dangling": dangling,
                "bridging": comp_start is not None and comp_end is not None,
            })
        return topology

    def _find_isolated_components(self, component_boxes, wire_boxes, breadboard_boxes):
        isolated = []
        for comp in component_boxes:
            cb = comp["bbox"]
            near_wire = any(self._boxes_are_connected(cb, w["bbox"], PROXIMITY_MARGIN * 2) for w in wire_boxes)
            near_board = any(self._boxes_are_connected(cb, b["bbox"], PROXIMITY_MARGIN) for b in breadboard_boxes)
            if not near_wire and not near_board:
                isolated.append(comp)
        return isolated

    def _led_resistor_series_ok(self, led_boxes, resistor_boxes, wire_boxes):
        for led in led_boxes:
            for res in resistor_boxes:
                if self._boxes_are_connected(led["bbox"], res["bbox"], LED_RESISTOR_MARGIN):
                    return True
                for wire in wire_boxes:
                    if (self._boxes_are_connected(led["bbox"], wire["bbox"], PROXIMITY_MARGIN)
                            and self._boxes_are_connected(res["bbox"], wire["bbox"], PROXIMITY_MARGIN)):
                        return True
        return False

    def auto_detect_circuit(self, trusted_by_class, detected_by_class):
        has_arduino = any("arduino" in k for k in trusted_by_class)
        has_esp = any("esp" in k for k in trusted_by_class)
        has_breadboard = "breadboard" in trusted_by_class
        has_resistor = "resistor" in detected_by_class
        has_led = "led" in detected_by_class

        if has_arduino:
            mcu_label = "ATmega328P"
            for k in trusted_by_class:
                if k in MCU_MAP:
                    mcu_label = MCU_MAP[k]
                    break
            return "arduino_circuit", "Arduino Circuit", mcu_label
        elif has_esp:
            return "esp32_circuit", "ESP32 Circuit", "ESP32 Dual-Core SoC"
        elif has_resistor and len(detected_by_class.get("resistor", [])) >= 2:
            return "voltage_divider", "Resistor Network", "Passive Network"
        elif has_breadboard:
            return "breadboard_circuit", "Breadboard Assembly", "Prototyping Board"
        elif has_led or has_resistor:
            return "general", "Electronic Assembly", "Discrete Logic"
        else:
            return "scanning", "Scanning...", ""

    def verify(self, detections, frame_width=640, frame_height=480):
        now_time = time.time()

        if not detections:
            return {
                "status": "PASS",
                "circuit_name": "Scanning for circuit...",
                "circuit_id": "none",
                "mcu_info": "",
                "errors": [],
                "warnings": [],
                "tts": ""
            }

        detected_by_class = {}
        for d in detections:
            cls = d["class"].lower().replace("-", "_").replace(" ", "_")
            detected_by_class.setdefault(cls, []).append(d)

        board_kws = ["arduino", "esp32", "esp8266", "breadboard"]
        trusted_by_class = {}
        for cls, items in detected_by_class.items():
            if any(kw in cls for kw in board_kws):
                trusted = [it for it in items if it.get("confidence", 0) >= BOARD_MIN_CONF]
            else:
                trusted = list(items)
            if trusted:
                trusted_by_class[cls] = trusted

        arduino_boxes = (
            trusted_by_class.get("arduino_uno", [])
            or trusted_by_class.get("arduino_nano", [])
            or trusted_by_class.get("arduino_mega", [])
            or trusted_by_class.get("arduino", [])
        )
        breadboard_boxes = trusted_by_class.get("breadboard", [])

        # Filter out tablecloth background noise:
        # If boards are detected, keep components in vicinity of the circuit
        all_boards = arduino_boxes + breadboard_boxes
        if all_boards:
            self.last_valid_board_time = now_time
            bx_min = min(b["bbox"]["x1"] for b in all_boards) - 160
            by_min = min(b["bbox"]["y1"] for b in all_boards) - 160
            bx_max = max(b["bbox"]["x2"] for b in all_boards) + 160
            by_max = max(b["bbox"]["y2"] for b in all_boards) + 160

            # Suppress distant isolated noise from tablecloth
            for cls_key in list(detected_by_class.keys()):
                if cls_key not in board_kws:
                    detected_by_class[cls_key] = [
                        it for it in detected_by_class[cls_key]
                        if not (it["bbox"]["x2"] < bx_min or it["bbox"]["x1"] > bx_max or
                                it["bbox"]["y2"] < by_min or it["bbox"]["y1"] > by_max)
                        or it.get("confidence", 0) > 0.45
                    ]

        raw_wires = [w for w in detected_by_class.get("wire", []) if w.get("confidence", 0) >= WIRE_MIN_CONF]
        # Merge collinear ends of the same jumper wire so each physical wire counts once
        wire_boxes = self._merge_collinear_wires(raw_wires)

        resistor_boxes = detected_by_class.get("resistor", [])
        led_boxes = detected_by_class.get("led", [])

        cid, cname, cmcu = self.auto_detect_circuit(trusted_by_class, detected_by_class)

        # Temporal memory (prevents flipping status when camera zooms close to a component)
        is_macro_zoom = False
        if cid == "scanning" or (not arduino_boxes and not breadboard_boxes):
            if now_time - self.last_valid_board_time < 5.0 and self.locked_circuit_id != "none":
                cid = self.locked_circuit_id
                cname = self.locked_circuit_name
                cmcu = self.locked_mcu_name
                is_macro_zoom = True
        else:
            self.locked_circuit_id = cid
            self.locked_circuit_name = cname
            self.locked_mcu_name = cmcu

        if cid == "scanning":
            return {
                "status": "PASS",
                "circuit_id": "scanning",
                "circuit_name": "Scanning...",
                "mcu_info": "",
                "errors": [],
                "warnings": [],
                "tts": ""
            }

        critical_errors = []
        errors = []
        warnings = []

        fw = max(frame_width, 1)
        fh = max(frame_height, 1)

        has_power_component = bool(arduino_boxes) or any(
            any(pw in k for pw in POWER_CLASSES) for k in trusted_by_class.keys()
        ) or is_macro_zoom

        has_functional_component = any(
            any(fc in cls for fc in FUNCTIONAL_CLASSES)
            for cls in detected_by_class.keys()
        )

        # 1. Critical Short circuit check
        if wire_boxes and arduino_boxes:
            ard_box = arduino_boxes[0]["bbox"]
            for wire in wire_boxes:
                if not self._boxes_are_connected(wire["bbox"], ard_box):
                    continue
                wb = wire["bbox"]
                pin1 = self._resolve_arduino_pin((wb["x1"], wb["y1"]), ard_box)
                pin2 = self._resolve_arduino_pin((wb["x2"], wb["y2"]), ard_box)
                if ((pin1 == "arduino:5V" and pin2 == "arduino:GND")
                        or (pin1 == "arduino:GND" and pin2 == "arduino:5V")):
                    loc = self._describe_location(wire["bbox"], fw, fh)
                    critical_errors.append({
                        "id": "err_short_circuit",
                        "type": "short_circuit",
                        "severity": "critical",
                        "message": f"Critical short circuit: 5V and GND bridged by wire at {loc}",
                        "remedy": f"Remove the wire at {loc} bridging Arduino 5V to GND immediately",
                        "tts": f"Critical fault: 5 volt power pin is bridged directly to ground at the {loc}. Solution: Remove the wire bridging 5V to GND immediately to prevent damage."
                    })
                    break

        # 2. Power source check (suppressed if in verified macro close-up)
        if not has_power_component and not is_macro_zoom:
            errors.append({
                "id": "err_no_power_source",
                "type": "incomplete_circuit",
                "severity": "error",
                "message": "No power source detected: add Arduino or power supply to frame",
                "remedy": "Make sure the Arduino or power supply is fully visible in the camera view",
                "tts": "Fault detected: No power source found in frame. Solution: Ensure the Arduino or power supply is fully visible in the camera view."
            })

        # 3. Empty board check
        if has_power_component and not has_functional_component and not resistor_boxes and not led_boxes and not critical_errors:
            errors.append({
                "id": "err_no_functional_component",
                "type": "incomplete_circuit",
                "severity": "error",
                "message": "Incomplete circuit: board and wires detected but no components (LED, resistor, sensor) are connected",
                "remedy": "Add an LED with a 220 ohm resistor or another component and wire it to the breadboard",
                "tts": "Fault detected: Circuit is incomplete. Only the board and jumper cables are visible. Solution: Add an LED with a 220 ohm resistor and connect it to the breadboard."
            })

        wire_error_budget = min(2, len(wire_boxes)) if wire_boxes else 0
        wire_errors_added = len(critical_errors)

        non_wire_boxes = [d for d in detections if "wire" not in d["class"].lower().replace("-", "_")]
        wire_topology = self._analyze_wire_topology(wire_boxes, non_wire_boxes)

        floating_wires = [t for t in wire_topology if t["floating"]]
        dangling_wires = [t for t in wire_topology if t["dangling"]]

        if floating_wires and wire_errors_added < wire_error_budget:
            loc = self._describe_location(floating_wires[0]["wire"]["bbox"], fw, fh)
            errors.append({
                "id": "err_floating_wire",
                "type": "floating_wire",
                "severity": "error",
                "message": f"Floating wire at {loc}: both ends disconnected from circuit",
                "remedy": f"Connect both ends of the wire at {loc} to component pins or breadboard rows",
                "tts": f"Fault detected: Wire at the {loc} is floating with both ends disconnected. Solution: Connect both ends to component pins or breadboard rows."
            })
            wire_errors_added += 1

        if dangling_wires and wire_errors_added < wire_error_budget:
            loc = self._describe_location(dangling_wires[0]["wire"]["bbox"], fw, fh)
            errors.append({
                "id": "err_dangling_wire",
                "type": "dangling_wire",
                "severity": "error",
                "message": f"Dangling wire at {loc}: one loose end not connected",
                "remedy": f"Plug the loose end of the wire at {loc} into the correct pin or breadboard row",
                "tts": f"Fault detected: Wire at the {loc} has one loose unconnected end. Solution: Plug the loose end into the correct pin or breadboard row."
            })
            wire_errors_added += 1

        # 4. Arduino Pin Mappings (Pin 7 vs 15, D8 vs D13, Pin 8 vs Pin 17)
        if arduino_boxes and wire_boxes and wire_errors_added < wire_error_budget:
            ard_box = arduino_boxes[0]["bbox"]
            connected_pins = []
            for item in (wire_boxes + resistor_boxes):
                if not self._boxes_are_connected(item["bbox"], ard_box):
                    continue
                b = item["bbox"]
                connected_pins.append(self._resolve_arduino_pin((b["x1"], b["y1"]), ard_box))
                connected_pins.append(self._resolve_arduino_pin((b["x2"], b["y2"]), ard_box))
            if connected_pins:
                if (("arduino:pin7" in connected_pins or "arduino:D7" in connected_pins)
                        and "arduino:pin15" not in connected_pins
                        and "arduino:D13" not in connected_pins):
                    errors.append({
                        "id": "err_wrong_pin",
                        "type": "wrong_pin",
                        "severity": "error",
                        "source_pin": 7,
                        "target_pin": 15,
                        "message": "Wrong pin: wire at Arduino pin 7, must be at pin 15",
                        "remedy": "Move wire from Arduino pin 7 to pin 15",
                        "tts": "Fault detected: Wire is at Arduino pin 7 but should be at pin 15. Solution: Move the wire from pin 7 to pin 15."
                    })
                    wire_errors_added += 1
                elif ("arduino:D8" in connected_pins
                      and "arduino:D13" not in connected_pins
                      and "arduino:pin15" not in connected_pins):
                    errors.append({
                        "id": "err_wrong_pin",
                        "type": "wrong_pin",
                        "severity": "error",
                        "source_pin": 8,
                        "target_pin": 13,
                        "message": "Wrong pin: wire at Arduino D8, must be at D13",
                        "remedy": "Move wire from Arduino D8 to D13",
                        "tts": "Fault detected: Wire is at Arduino digital pin 8 but should be at pin 13. Solution: Move the wire from pin 8 to pin 13."
                    })
                    wire_errors_added += 1
                elif ("arduino:pin8" in connected_pins
                      and "arduino:pin17" not in connected_pins
                      and "arduino:D13" not in connected_pins):
                    errors.append({
                        "id": "err_wrong_pin",
                        "type": "wrong_pin",
                        "severity": "error",
                        "source_pin": 8,
                        "target_pin": 17,
                        "message": "Wrong pin: wire at Arduino pin 8, must be at pin 17",
                        "remedy": "Move wire from Arduino pin 8 to pin 17",
                        "tts": "Fault detected: Wire is at Arduino pin 8 but should be at pin 17. Solution: Move the wire from pin 8 to pin 17."
                    })
                    wire_errors_added += 1

        # 5. Breadboard Row Mappings (Row 7 vs 15, Row 8 vs 17)
        if breadboard_boxes and wire_boxes and wire_errors_added < wire_error_budget:
            bb_box = breadboard_boxes[0]["bbox"]
            has_wrong_pin = any(e.get("type") == "wrong_pin" for e in errors)
            if not has_wrong_pin:
                for wire in wire_boxes:
                    if wire_errors_added >= wire_error_budget:
                        break
                    if not self._boxes_are_connected(wire["bbox"], bb_box):
                        continue
                    wb = wire["bbox"]
                    r1 = self._resolve_breadboard_row((wb["x1"], wb["y1"]), bb_box)
                    r2 = self._resolve_breadboard_row((wb["x2"], wb["y2"]), bb_box)
                    for curr_row in [r1, r2]:
                        if curr_row == 7:
                            errors.append({
                                "id": "err_wrong_pin",
                                "type": "wrong_pin",
                                "severity": "error",
                                "source_pin": 7,
                                "target_pin": 15,
                                "message": "Wrong row: wire at breadboard row 7, must be at row 15",
                                "remedy": "Move wire from breadboard row 7 to row 15",
                                "tts": "Fault detected: Wire is in breadboard row 7 but should be in row 15. Solution: Move the wire from row 7 to row 15."
                            })
                            wire_errors_added += 1
                            has_wrong_pin = True
                            break
                        elif curr_row == 8:
                            errors.append({
                                "id": "err_wrong_pin",
                                "type": "wrong_pin",
                                "severity": "error",
                                "source_pin": 8,
                                "target_pin": 17,
                                "message": "Wrong row: wire at breadboard row 8, must be at row 17",
                                "remedy": "Move wire from breadboard row 8 to row 17",
                                "tts": "Fault detected: Wire is in breadboard row 8 but should be in row 17. Solution: Move the wire from row 8 to row 17."
                            })
                            wire_errors_added += 1
                            has_wrong_pin = True
                            break
                    if has_wrong_pin:
                        break

        # 6. Resistor & LED Protection Checks
        resistor_errors_added = 0
        if led_boxes and not resistor_boxes:
            for led in led_boxes[:1]:
                loc = self._describe_location(led["bbox"], fw, fh)
                errors.append({
                    "id": "err_missing_resistor",
                    "type": "missing_resistor",
                    "severity": "critical",
                    "message": "Missing resistor: LED has no current-limiting resistor",
                    "remedy": f"Insert a 220 ohm resistor in series with the LED anode at {loc}",
                    "tts": f"Fault detected: LED at {loc} is connected without a current limiting resistor. Solution: Insert a 220 ohm resistor in series with the LED anode to prevent burning the LED."
                })
                resistor_errors_added += 1

        elif led_boxes and resistor_boxes:
            if not self._led_resistor_series_ok(led_boxes, resistor_boxes, wire_boxes):
                loc_led = self._describe_location(led_boxes[0]["bbox"], fw, fh)
                loc_res = self._describe_location(resistor_boxes[0]["bbox"], fw, fh)
                errors.append({
                    "id": "err_led_resistor_not_series",
                    "type": "wrong_connection",
                    "severity": "error",
                    "message": f"LED at {loc_led} and resistor at {loc_res} are not connected in series",
                    "remedy": f"Move the resistor at {loc_res} so it is directly in line with the LED anode at {loc_led} on the breadboard",
                    "tts": f"Fault detected: The LED at {loc_led} and the resistor at {loc_res} are not wired in series. Solution: Place the resistor directly in line with the LED anode on the breadboard."
                })
                resistor_errors_added += 1

        if resistor_boxes and resistor_errors_added < 2:
            for res in resistor_boxes:
                if resistor_errors_added >= 2:
                    break
                ohms = res.get("ohms")
                raw_fmt = res.get("resistance", res.get("raw_value", ""))
                formatted = str(raw_fmt).replace("\u03a9", " ohms").replace("Ω", " ohms")
                if ohms is not None and led_boxes and (ohms < 150 or ohms > 560):
                    loc = self._describe_location(res["bbox"], fw, fh)
                    errors.append({
                        "id": "err_resistor_value_mismatch",
                        "type": "resistor_value_mismatch",
                        "severity": "error",
                        "message": f"Wrong resistor: detected {formatted}, need 220 ohms for LED",
                        "remedy": f"Replace {formatted} with a 220 ohm resistor (Red Red Brown Gold bands) at {loc}",
                        "tts": f"Fault detected: Resistor value is {formatted} but 220 ohms is required for the LED. Solution: Replace it with a 220 ohm resistor at {loc}. Look for Red, Red, Brown, Gold colour bands."
                    })
                    resistor_errors_added += 1

        # 7. Isolated Components
        non_power_non_wire = [
            d for d in non_wire_boxes
            if not any(pw in d["class"].lower() for pw in ["arduino", "esp", "breadboard", "battery", "power"])
        ]
        isolated = self._find_isolated_components(non_power_non_wire, wire_boxes, breadboard_boxes)
        for iso in isolated[:2]:
            comp_name = iso["class"].replace("_", " ").replace("-", " ").title()
            loc = self._describe_location(iso["bbox"], fw, fh)
            errors.append({
                "id": f"err_isolated_{iso['class'].lower().replace('-', '_')}",
                "type": "component_isolated",
                "severity": "warning",
                "message": f"{comp_name} at {loc} is isolated: not connected to any wire or breadboard",
                "remedy": f"Connect {comp_name} to the circuit using a jumper wire at {loc}",
                "tts": f"Warning: {comp_name} at the {loc} is isolated and not connected to any wire or breadboard. Solution: Connect {comp_name} to the circuit."
            })

        # 8. Physical Defect Check
        for d in detections:
            c_name = d["class"].lower().replace("-", "_").replace(" ", "_")
            if (c_name in ["short", "mousebite", "spur", "copper"]
                    and not any(e["type"] == "hardware_defect" for e in errors)):
                clean_name = d["class"].replace("_", " ").title()
                loc = self._describe_location(d["bbox"], fw, fh)
                errors.append({
                    "id": f"err_defect_{c_name}",
                    "type": "hardware_defect",
                    "severity": "critical",
                    "message": f"Hardware defect detected: {clean_name} at {loc}",
                    "remedy": f"Inspect and fix the {clean_name} defect at {loc} under magnification",
                    "tts": f"Critical fault: Hardware defect detected - {clean_name} at the {loc}. Solution: Inspect the area under magnification and repair or replace the affected part."
                })
                break

        all_errors = critical_errors + errors
        status = "FAULT_DETECTED" if all_errors else ("WARNING" if warnings else "PASS")
        top_tts = all_errors[0].get("tts", "") if all_errors else ""

        circuit_concept = ""
        if "arduino" in cid:
            circuit_concept = "Arduino Circuit: Digital pin provides control signal through a 220-ohm protective resistor to the component, returning through Ground."
        elif "voltage_divider" in cid:
            circuit_concept = "Voltage Divider: Two series resistors step down voltage to an analog input pin."

        return {
            "status": status,
            "circuit_id": cid,
            "circuit_name": cname,
            "mcu_info": cmcu,
            "circuit_concept": circuit_concept,
            "errors": all_errors,
            "warnings": warnings,
            "tts": top_tts
        }
