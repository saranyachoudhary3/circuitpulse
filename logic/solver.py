import os
import cv2
import numpy as np
from logic.grid import BreadboardGrid
from detectors.wires import WireTracer

class CircuitSolver:
    """
    Universal circuit solver. Provides rule-based component detection and
    visual-inspection status reporting. Deep error analysis is delegated to the VLM module.
    This solver handles: component inventory, power state, breadboard mapping,
    and basic connectivity checks.
    """
    def __init__(self):
        self.circuits = {}
        self.power_history = []
        self.last_status = "scanning"
        self.component_history = {}

    def _is_mcu_powered(self, crop):
        """Detect power LEDs on MCU boards using HSV color masking.
        Only works reliably on a CROPPED MCU bounding box, NOT on a full frame."""
        if crop is None or crop.size == 0:
            return False
        
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        
        # Green LED (power indicator)
        mask_g = cv2.inRange(hsv, (40, 150, 200), (90, 255, 255))
        # Orange/Yellow LED (L pin / activity)
        mask_y = cv2.inRange(hsv, (15, 150, 200), (35, 255, 255))
        # Red LED (TX/RX or Power)
        mask_r1 = cv2.inRange(hsv, (0, 150, 200), (10, 255, 255))
        mask_r2 = cv2.inRange(hsv, (170, 150, 200), (180, 255, 255))
        # Blue LED (some boards)
        mask_b = cv2.inRange(hsv, (100, 150, 200), (130, 255, 255))
        
        total = (cv2.countNonZero(mask_g) + cv2.countNonZero(mask_y) + 
                 cv2.countNonZero(mask_r1) + cv2.countNonZero(mask_r2) +
                 cv2.countNonZero(mask_b))
        
        # Need at least 4 bright LED pixels within the MCU crop
        return total > 3

    def _classify_circuit(self, detections):
        """Attempt to classify the circuit type from detected components."""
        classes = [d['class'].lower() for d in detections]
        has_mcu = any(c in ['arduino_uno', 'arduino_nano', 'arduino_mega', 'esp32'] for c in classes)
        has_bb = 'breadboard' in classes
        has_led = 'led' in classes
        has_resistor = 'resistor' in classes
        has_wire = 'wire' in classes
        has_motor = 'motor' in classes
        has_sensor = any(c in ['sensor', 'ultrasonic', 'pir', 'ldr', 'potentiometer'] for c in classes)
        has_display = any(c in ['lcd', 'oled', 'display', '7segment'] for c in classes)
        has_buzzer = 'buzzer' in classes
        has_relay = 'relay' in classes
        has_capacitor = 'capacitor' in classes
        
        if has_mcu and has_led and has_resistor:
            return "LED Circuit", "Microcontroller driving an LED with a current-limiting resistor"
        elif has_mcu and has_motor:
            return "Motor Control", "Microcontroller controlling a motor"
        elif has_mcu and has_sensor:
            return "Sensor Circuit", "Microcontroller reading sensor data"
        elif has_mcu and has_display:
            return "Display Circuit", "Microcontroller driving a display"
        elif has_mcu and has_buzzer:
            return "Buzzer Circuit", "Microcontroller driving a buzzer/speaker"
        elif has_mcu and has_relay:
            return "Relay Control", "Microcontroller controlling a relay"
        elif has_mcu and has_led:
            return "LED Circuit (No Resistor)", "LED connected to microcontroller - may need current-limiting resistor"
        elif has_mcu and has_bb:
            return "Prototyping", "Microcontroller with breadboard - circuit in progress"
        elif has_mcu:
            return "MCU Standalone", "Microcontroller detected - add components to build a circuit"
        elif has_bb:
            return "Breadboard Only", "Breadboard detected - add a microcontroller to begin"
        else:
            return "Scanning", "Looking for circuit components..."

    def verify(self, detections, frame=None, frame_width=640, frame_height=480):
        if not detections:
            return {
                "status": "FAULT_DETECTED",
                "circuit_id": "no_components",
                "circuit_name": "No Components Detected",
                "circuit_concept": "Point camera at a circuit board",
                "mcu_info": "No MCU",
                "errors": [{"message": "No Components", "remedy": "No circuit components detected in the camera view."}],
                "warnings": [],
                "tts": "No circuit components detected.",
                "tutor_mode": False,
                "is_powered": False,
                "components_summary": {},
                "electrical_status": "INDETERMINATE",
                "evidence_mode": "camera_heuristic",
                "electrical_note": "No circuit topology has been confirmed. Camera detection cannot establish electrical continuity."
            }

        # Component inventory
        mcu_boxes = [d for d in detections if d['class'].lower() in ['arduino_uno', 'arduino_nano', 'arduino_mega', 'esp32']]
        bb_boxes = [d for d in detections if d['class'].lower() == 'breadboard']
        leds = [d for d in detections if d['class'].lower() == 'led']
        resistors = [d for d in detections if d['class'].lower() == 'resistor']
        wires = [d for d in detections if d['class'].lower() == 'wire']
        other = [d for d in detections if d['class'].lower() not in ['arduino_uno', 'arduino_nano', 'arduino_mega', 'esp32', 'breadboard', 'led', 'resistor', 'wire']]

        has_mcu = len(mcu_boxes) > 0
        has_bb = len(bb_boxes) > 0
        is_powered = False
        
        # Power detection -- ONLY on the MCU crop, never on the full frame.
        # Full-frame scanning causes false positives from colored objects on the desk.
        if has_mcu and frame is not None:
            mb = mcu_boxes[0]['bbox']
            pad = 20
            y1, y2 = max(0, int(mb['y1'])-pad), min(frame_height, int(mb['y2'])+pad)
            x1, x2 = max(0, int(mb['x1'])-pad), min(frame_width, int(mb['x2'])+pad)
            current_power = self._is_mcu_powered(frame[y1:y2, x1:x2])
            self.power_history.append(1 if current_power else 0)
        else:
            # No MCU detected = no power. Period.
            self.power_history.append(0)
            
        if len(self.power_history) > 5:
            self.power_history.pop(0)
        is_powered = sum(self.power_history) >= 3

        # Breadboard pin mapping
        led_on_bb = False
        resistor_on_bb = False
        series_connected = False
        wiring_errors = []
        
        led_row_1, led_row_2 = None, None
        res_row_1, res_row_2 = None, None

        wire_to_mcu_count = 0
        wire_to_bb_count = 0

        grid = None
        if has_bb:
            grid = BreadboardGrid(bb_boxes[0]['bbox'])
            
            if leds:
                p1, p2 = grid.get_component_pins(leds[0]['bbox'])
                if p1 is not None and p2 is not None:
                    led_on_bb = True
                    led_row_1, led_row_2 = p1['row'], p2['row']
                    
            if resistors:
                p1, p2 = grid.get_component_pins(resistors[0]['bbox'])
                if p1 is not None and p2 is not None:
                    resistor_on_bb = True
                    res_row_1, res_row_2 = p1['row'], p2['row']

            # Series connection check
            if led_on_bb and resistor_on_bb:
                if led_row_1 in [res_row_1, res_row_2] or led_row_2 in [res_row_1, res_row_2]:
                    series_connected = True

            # Wire endpoint analysis
            if has_mcu and has_bb and frame is not None:
                mcu_box = mcu_boxes[0]['bbox']
                
                for w in wires:
                    ep1, ep2 = WireTracer.get_endpoints(frame, w['bbox'])
                    if not ep1 or not ep2:
                        continue
                    
                    ep1_in_mcu = (mcu_box['x1'] <= ep1[0] <= mcu_box['x2'] and mcu_box['y1'] <= ep1[1] <= mcu_box['y2'])
                    ep2_in_mcu = (mcu_box['x1'] <= ep2[0] <= mcu_box['x2'] and mcu_box['y1'] <= ep2[1] <= mcu_box['y2'])
                    
                    pin1 = grid.get_pin_location(*ep1) if not ep1_in_mcu else None
                    pin2 = grid.get_pin_location(*ep2) if not ep2_in_mcu else None
                    
                    if ep1_in_mcu or ep2_in_mcu:
                        wire_to_mcu_count += 1
                    if pin1 or pin2:
                        wire_to_bb_count += 1

        # Build component summary
        components_summary = {
            "mcu": len(mcu_boxes),
            "breadboard": len(bb_boxes),
            "led": len(leds),
            "resistor": len(resistors),
            "wire": len(wires),
            "other": len(other),
            "is_powered": is_powered,
            "led_on_breadboard": led_on_bb,
            "resistor_on_breadboard": resistor_on_bb,
            "series_connected": series_connected
        }

        # Circuit classification
        circuit_name, circuit_desc = self._classify_circuit(detections)
        mcu_info = mcu_boxes[0]['class'].replace('_', ' ').title() if has_mcu else "No MCU"

        # ----- RULE-BASED ERROR CHECKS -----
        errors = []
        warnings = []

        # 1. Power check: MCU detected but not powered
        if has_mcu and not is_powered:
            errors.append({
                "message": "MCU Not Powered",
                "remedy": "Connect the USB cable to the microcontroller to power it on."
            })
        
        # 2. LED without resistor
        if leds and not resistors and has_bb:
            errors.append({
                "message": "LED Without Current-Limiting Resistor",
                "remedy": "Add a 220-ohm resistor in series with the LED to prevent burnout."
            })
        
        # 3. LED and resistor not in series
        if led_on_bb and resistor_on_bb and not series_connected:
            errors.append({
                "message": "LED and Resistor Not in Series",
                "remedy": "The LED and resistor must share a breadboard row to be connected in series."
            })

        # 4. No wires between MCU and breadboard
        if has_mcu and has_bb and len(wires) == 0:
            errors.append({
                "message": "No Wires Detected",
                "remedy": "Connect jumper wires between the microcontroller and the breadboard."
            })

        # 5. MCU + breadboard but no wires reach the MCU
        if has_mcu and has_bb and len(wires) > 0 and wire_to_mcu_count == 0:
            warnings.append({
                "message": "No Wires Connected to MCU",
                "remedy": "Jumper wires are detected but none appear to reach the microcontroller pins."
            })

        # 6. Wires detected but no MCU and no breadboard -- jumbled/random wires
        if not has_mcu and not has_bb and len(wires) > 0:
            warnings.append({
                "message": "Loose Wires -- No Circuit",
                "remedy": "Wires detected but no microcontroller or breadboard found. Build a circuit first."
            })

        # 7. Breadboard with components but no MCU
        if has_bb and not has_mcu and (len(leds) > 0 or len(resistors) > 0):
            errors.append({
                "message": "No Microcontroller Detected",
                "remedy": "Connect a microcontroller (Arduino, ESP32) to drive the circuit."
            })

        # 8. Only a breadboard, nothing else
        if has_bb and not has_mcu and len(leds) == 0 and len(resistors) == 0 and len(wires) == 0:
            warnings.append({
                "message": "Empty Breadboard",
                "remedy": "Breadboard detected but no components or wires. Add components to build a circuit."
            })

        # ----- BUILD TUTOR MODE STEPS -----
        steps = []
        step_index = 0
        
        if has_mcu:
            steps.append({'title': 'Power', 'desc': 'Connect USB to power the MCU.', 'done': is_powered})
            if is_powered:
                step_index = 1
        
        if has_bb:
            steps.append({'title': 'Breadboard', 'desc': 'Breadboard detected.', 'done': has_bb})
            if has_bb and is_powered:
                step_index = max(step_index, 2)
        
        if leds:
            steps.append({'title': 'LED', 'desc': 'LED placed on breadboard.', 'done': led_on_bb})
            if led_on_bb and step_index >= 2:
                step_index = 3
        
        if resistors:
            steps.append({'title': 'Resistor', 'desc': 'Resistor in series with LED.', 'done': series_connected})
            if series_connected and step_index >= 3:
                step_index = 4
        
        if wires:
            all_wired = len(wires) >= 2 and wire_to_mcu_count >= 1
            steps.append({'title': 'Wiring', 'desc': 'Complete the wire connections.', 'done': all_wired})
            if all_wired and step_index >= 4:
                step_index = 5

        completed_steps = [s for s in steps if s['done']]
        pending_steps = [s for s in steps if not s['done']]

        # ----- DETERMINE OVERALL STATUS -----
        has_critical = len(errors) > 0
        has_warnings = len(warnings) > 0

        # A circuit is only PASS if:
        #   - There is at least an MCU
        #   - The MCU is powered
        #   - There are zero errors
        #   - All tutor steps are complete
        all_done = len(pending_steps) == 0 and len(steps) > 0

        if has_critical:
            status = "FAULT_DETECTED"
            tts = errors[0]['remedy']
        elif has_warnings:
            status = "FAULT_DETECTED"
            tts = warnings[0]['remedy']
        elif all_done and has_mcu and is_powered:
            status = "PASS"
            tts = "Circuit appears complete."
        else:
            # Not enough info to declare PASS. Default to fault.
            status = "FAULT_DETECTED"
            tts = "Circuit incomplete. Check connections and power."

        current_step = pending_steps[0] if pending_steps else None

        return {
            'status': status,
            'circuit_id': circuit_name.lower().replace(' ', '_'),
            'circuit_name': circuit_name,
            'circuit_concept': circuit_desc,
            'mcu_info': mcu_info,
            'errors': errors + warnings,
            'warnings': [],
            'tts': tts,
            'tutor_mode': True,
            'is_powered': is_powered,
            'current_step': current_step,
            'pending_steps': pending_steps[1:] if pending_steps else [],
            'completed_steps': completed_steps,
            'components_summary': components_summary,
            # A bounding-box and colour analysis can identify likely placement,
            # but it cannot prove that two conductors are electrically joined.
            # Only the explicit-netlist verifier may return electrical PASS.
            'electrical_status': 'INDETERMINATE',
            'evidence_mode': 'camera_heuristic',
            'electrical_note': 'Visual inspection only. Confirm the topology with the netlist verifier before treating this as electrically validated.'
        }
