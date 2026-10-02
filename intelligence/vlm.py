import os
import cv2
import json
import time
import base64
import threading
import traceback
import numpy as np
from intelligence.knowledge import get_full_knowledge_base

CLASS_COLORS = {
    'arduino_uno': (204, 255, 0),
    'arduino_nano': (204, 255, 0),
    'arduino_mega': (204, 255, 0),
    'esp32': (204, 255, 0),
    'breadboard': (255, 255, 255),
    'led': (0, 204, 255),
    'resistor': (255, 170, 0),
    'wire': (255, 0, 255),
}

KNOWLEDGE_BASE = get_full_knowledge_base()


class CircuitAnalyzer:
    """
    Optional cloud explanation layer with:
    - Deep circuit theory knowledge base
    - Multi-turn conversation memory (tracks analysis history)
    - Correct circuit reference generation
    - Breadboard row-level mapping from YOLO detections
    - Progressive fix tracking across re-analyses
    """

    def __init__(self):
        self.model = None
        self.api_available = False
        self.latest_analysis = None
        self.last_analysis_time = 0
        self.analysis_interval = 4
        self.lock = threading.Lock()
        self.analysis_count = 0
        self.completed_steps = set()
        self._analyzing = False
        self._previous_status = None
        # Multi-turn memory
        self._analysis_history = []  # Last N analysis summaries
        self._max_history = 5
        self._identified_circuit_type = None
        self._user_question = None  # For on-demand Q&A
        self._init_model()

    def _init_model(self):
        # Electrical verdicts never depend on this service.  Keep cloud
        # traffic off by default so an offline rehearsal has no implicit
        # network dependency.  An operator may opt in explicitly for prose
        # explanations after the deterministic graph actor has produced its
        # finding.
        if os.environ.get("CIRCUITPULSE_ENABLE_CLOUD_EXPLAINER") != "1":
            print("[VLM] Cloud explainer disabled; deterministic local verification remains active.")
            return
        try:
            import google.generativeai as genai
            api_key = os.environ.get("GEMINI_API_KEY", "")
            if not api_key:
                print("[VLM] Cloud explainer requested but GEMINI_API_KEY is unavailable.")
                return
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel("gemini-3.6-flash")
            self.api_available = True
            print("[VLM] Gemini 2.0 Flash initialized. Advanced circuit intelligence ACTIVE.")
        except ImportError:
            print("[VLM] google-generativeai not installed. pip install google-generativeai")
        except Exception as e:
            print(f"[VLM] Init error: {e}")

    def ask_question(self, question):
        """Queue a user question for the next analysis cycle."""
        self._user_question = question
        self.last_analysis_time = 0  # Force immediate re-analysis

    def _annotate_frame(self, frame, detections):
        annotated = frame.copy()
        for d in detections:
            bbox = d['bbox']
            x1, y1, x2, y2 = int(bbox['x1']), int(bbox['y1']), int(bbox['x2']), int(bbox['y2'])
            cls = d['class'].lower()
            color = CLASS_COLORS.get(cls, (128, 128, 128))
            conf = d.get('confidence', 0)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            label = f"{d['class']} {conf:.0%}"
            if d.get('resistance'):
                label += f" [{d['resistance']}]"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(annotated, (x1, y1 - th - 8), (x1 + tw + 6, y1), (0, 0, 0), -1)
            cv2.putText(annotated, label, (x1 + 3, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
            if d.get('endpoints') and len(d['endpoints']) == 2:
                ep1, ep2 = d['endpoints']
                cv2.circle(annotated, (int(ep1[0]), int(ep1[1])), 5, (255, 0, 255), -1)
                cv2.circle(annotated, (int(ep2[0]), int(ep2[1])), 5, (255, 0, 255), -1)
                cv2.line(annotated, (int(ep1[0]), int(ep1[1])), (int(ep2[0]), int(ep2[1])), (255, 0, 255), 1)
        return annotated

    def _encode_frame(self, frame):
        h, w = frame.shape[:2]
        if w > 800:
            scale = 800 / w
            frame = cv2.resize(frame, (800, int(h * scale)))
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return base64.b64encode(buf.tobytes()).decode("utf-8")

    def analyze(self, frame, detections):
        if not self.api_available or self.model is None:
            return None
        now = time.time()
        if now - self.last_analysis_time < self.analysis_interval:
            with self.lock:
                return self.latest_analysis
        if self._analyzing:
            with self.lock:
                return self.latest_analysis
        self.last_analysis_time = now
        thread = threading.Thread(
            target=self._run_analysis, args=(frame.copy(), list(detections)),
            daemon=True
        )
        thread.start()
        with self.lock:
            return self.latest_analysis

    def _build_component_summary(self, detections):
        lines = []
        for d in detections:
            entry = f"- {d['class']} (confidence: {d['confidence']:.0%})"
            bbox = d['bbox']
            entry += f" [bbox: ({bbox['x1']},{bbox['y1']})-({bbox['x2']},{bbox['y2']})]"
            if d.get("resistance"):
                entry += f" [Resistance: {d['resistance']}]"
            if d.get("bands_str"):
                entry += f" [Color bands: {d['bands_str']}]"
            if d.get("endpoints"):
                ep = d["endpoints"]
                entry += f" [Wire endpoints: ({ep[0][0]},{ep[0][1]}) to ({ep[1][0]},{ep[1][1]})]"
            lines.append(entry)
        return "\n".join(lines) if lines else "No components detected by YOLO yet."

    def _build_breadboard_map(self, detections):
        """Map detected components to approximate breadboard rows using spatial analysis."""
        bb = None
        for d in detections:
            if d['class'].lower() == 'breadboard':
                bb = d['bbox']
                break
        if not bb:
            return ""

        bb_x1, bb_y1 = bb['x1'], bb['y1']
        bb_w = max(1, bb['x2'] - bb['x1'])
        bb_h = max(1, bb['y2'] - bb['y1'])
        is_horizontal = bb_w > bb_h

        lines = ["\nBREADBOARD ROW MAPPING (approximate from bounding box positions):"]
        for d in detections:
            cls = d['class'].lower()
            if cls == 'breadboard':
                continue
            dbbox = d['bbox']
            # Compute center of component relative to breadboard
            cx = ((dbbox['x1'] + dbbox['x2']) / 2 - bb_x1)
            cy = ((dbbox['y1'] + dbbox['y2']) / 2 - bb_y1)

            if is_horizontal:
                # Row is determined by horizontal position
                row = int((cx / bb_w) * 30) + 1
                row = max(1, min(30, row))
                side = "top" if cy < bb_h / 2 else "bottom"
                # For components spanning multiple rows
                left_row = int(((dbbox['x1'] - bb_x1) / bb_w) * 30) + 1
                right_row = int(((dbbox['x2'] - bb_x1) / bb_w) * 30) + 1
                left_row = max(1, min(30, left_row))
                right_row = max(1, min(30, right_row))
            else:
                row = int((cy / bb_h) * 30) + 1
                row = max(1, min(30, row))
                side = "left" if cx < bb_w / 2 else "right"
                left_row = int(((dbbox['y1'] - bb_y1) / bb_h) * 30) + 1
                right_row = int(((dbbox['y2'] - bb_y1) / bb_h) * 30) + 1
                left_row = max(1, min(30, left_row))
                right_row = max(1, min(30, right_row))

            if left_row == right_row:
                lines.append(f"- {d['class']}: row {row}, {side} half")
            else:
                lines.append(f"- {d['class']}: spans rows {left_row}-{right_row}, {side} half")

        return "\n".join(lines) if len(lines) > 1 else ""

    def _build_history_context(self):
        """Build multi-turn conversation memory from analysis history."""
        if not self._analysis_history:
            return ""
        parts = ["\nANALYSIS HISTORY (most recent last -- use this to track user progress):"]
        for h in self._analysis_history[-self._max_history:]:
            parts.append(
                f"- Scan #{h['id']} at {h['time']}: "
                f"status={h['status']}, "
                f"circuit={h['circuit']}, "
                f"errors={h['n_errors']}"
                f"{', fixes_applied=' + h.get('fixes_applied', '') if h.get('fixes_applied') else ''}"
            )
        if self.completed_steps:
            parts.append(f"- Issues resolved so far: {', '.join(sorted(self.completed_steps))}")
        parts.append("- Use this history to avoid repeating already-fixed errors and to acknowledge progress.")
        return "\n".join(parts)

    def _build_question_section(self):
        """If user asked a question, add it to the prompt."""
        if not self._user_question:
            return ""
        q = self._user_question
        self._user_question = None  # Consume the question
        return f"""

USER QUESTION (answer this in the "answer" field of your JSON response):
"{q}"

Add this field to your JSON response:
"answer": "your detailed answer to the user's question about the circuit"
"""

    def _run_analysis(self, frame, detections):
        self._analyzing = True
        try:
            annotated = self._annotate_frame(frame, detections)
            b64_img = self._encode_frame(annotated)
            components_text = self._build_component_summary(detections)
            bb_map = self._build_breadboard_map(detections)
            history = self._build_history_context()
            question = self._build_question_section()

            prompt = f"""You are CircuitPulse, a world-class electronics engineer and circuit debugger with 20 years of hands-on breadboard prototyping experience. You can look at ANY breadboard circuit and instantly identify every component, trace every wire, and find every mistake.

You are analyzing a physical breadboard circuit from a camera photograph. The image has YOLO detection bounding boxes overlaid (colored rectangles with labels). Note: YOLO only detects 8 classes (arduino_uno/nano/mega, esp32, breadboard, resistor, wire, led). Components NOT in this list (capacitors, transistors, ICs, sensors, motors, buzzers, buttons, potentiometers, displays, etc.) will NOT have bounding boxes -- you MUST identify them yourself from the raw image.

DETECTED COMPONENTS (from YOLO with bounding box coordinates):
{components_text}
{bb_map}
{KNOWLEDGE_BASE}
{history}

===== YOUR MANDATORY ANALYSIS PROCESS =====

STEP 1 - COMPONENT INVENTORY:
Look at the ENTIRE image. List every single component you can see, whether YOLO detected it or not. For each component, note:
- What it is (exact type: e.g., "red LED", "220 ohm resistor with red-red-brown bands", "Arduino Uno R3")
- Where it is on the breadboard (which rows, which side)
- Its orientation (polarity for LEDs/caps, pin 1 for ICs)

STEP 2 - CIRCUIT IDENTIFICATION:
Based on the components present and their arrangement, determine exactly what circuit is being built. Name it specifically (e.g., "LED Blink Circuit", "Button-Controlled LED", "Voltage Divider", "Motor H-Bridge Driver").

STEP 3 - WIRE-BY-WIRE CONNECTION TRACING:
For EVERY wire visible in the image:
- Identify its color
- Identify where each end connects (specific MCU pin or specific breadboard row)
- Determine what electrical purpose this wire serves (power, ground, signal, data)
For EVERY component:
- Identify which breadboard rows its pins occupy
- Determine what other components or wires share those rows (and are therefore electrically connected)

STEP 4 - EXPECTED vs ACTUAL COMPARISON:
Based on what circuit this SHOULD be:
- List every connection that SHOULD exist
- Check each one against what you actually see
- Identify MISSING connections (wires that should be there but aren't)
- Identify WRONG connections (wires going to the wrong row or pin)
- Identify EXTRA connections (wires that shouldn't be there)
- Check component values (is the resistor the right value?)
- Check component orientation (is the LED the right way around?)

STEP 5 - POWER PATH VERIFICATION:
- Is the MCU connected to power? (USB cable plugged in, or external supply)
- Is the breadboard power rail connected to MCU 5V/3.3V?
- Is the breadboard ground rail connected to MCU GND?
- Does every component have a complete circuit path from power through itself back to ground?

STEP 6 - GENERATE FIX INSTRUCTIONS:
For each error found, write a specific physical instruction that a beginner can follow. Reference exact breadboard rows, exact MCU pins, exact wire colors. Each step should be ONE physical action (move one wire, add one component, etc.).
{question}
Respond ONLY with valid JSON (no markdown, no backticks, no explanation outside JSON):
{{
  "circuit_type": "specific circuit name (e.g. 'Arduino LED Blink Circuit')",
  "circuit_description": "1-2 sentences: what this circuit does when wired correctly",
  "circuit_logic": "Explain the electrical theory: how current flows, what each component does, why each component is needed. Write 3-5 sentences a student would understand. Example: 'When Arduino pin 13 goes HIGH, 5V flows through the 220-ohm resistor which limits current to about 20mA, then through the LED (forward voltage ~2V), and returns to ground. Without the resistor, the LED would draw too much current and burn out. The Arduino toggles pin 13 on and off every second, creating the blink effect.'",
  "components_found": ["list EVERY component visible in the image, be specific about type and value"],
  "components_yolo_missed": ["list components you identified that YOLO did not detect"],
  "status": "WORKING" or "HAS_ERRORS" or "INCOMPLETE",
  "topology": {{
    "power_path": "exactly how power flows: e.g. 'USB to Arduino 5V pin -> orange wire to breadboard row 1 (+) rail -> ...'",
    "ground_path": "exactly how ground returns: e.g. 'Component cathode in row 15 -> blue wire to (-) rail -> black wire to Arduino GND'",
    "signal_path": "exactly how signals flow: e.g. 'Arduino pin 13 -> yellow wire to breadboard row 7 -> through 220ohm resistor to row 10 -> LED anode in row 10'"
  }},
  "correct_wiring": {{
    "description": "Describe the CORRECT way to build this circuit from scratch, as if teaching a complete beginner who has never used a breadboard before",
    "connections": [
      "1. Plug the Arduino Uno into USB to power it. The green power LED should turn on.",
      "2. Connect a jumper wire from Arduino 5V pin to the red (+) power rail on the breadboard",
      "3. Connect a jumper wire from Arduino GND pin to the blue (-) ground rail on the breadboard",
      "4. Insert the LED into the breadboard: long leg (anode, +) into row 10 hole e, short leg (cathode, -) into row 11 hole e",
      "5. Insert the 220-ohm resistor (red-red-brown bands): one leg into row 7 hole a, other leg into row 10 hole a (this connects it to the LED anode row)",
      "6. Connect a jumper wire from Arduino pin 13 to breadboard row 7 (this feeds signal into the resistor)",
      "7. Connect a jumper wire from breadboard row 11 (LED cathode row) to the blue (-) ground rail"
    ]
  }},
  "errors": [
    {{
      "severity": "CRITICAL" or "WARNING" or "INFO",
      "component": "which specific component (e.g. 'red LED' not just 'LED')",
      "issue": "what is wrong -- use specific breadboard rows, pin numbers, wire colors. e.g. 'The red wire connects Arduino pin 13 to row 15 but the LED anode is in row 10, so there is no electrical connection between the signal and the LED'",
      "fix": "exact physical action: e.g. 'Move the red wire from row 15 to row 7, where the resistor input leg is'",
      "why": "electrical consequence: e.g. 'Without this connection, no current can flow from the Arduino to the LED, so it will never light up'"
    }}
  ],
  "fix_steps": [
    {{
      "step": 1,
      "title": "short action title (e.g. 'Move the red wire')",
      "instruction": "Detailed physical instruction: e.g. 'Pull out the red wire from breadboard row 15. Plug one end into Arduino digital pin 13. Plug the other end into breadboard row 7, any hole on the left side (a-e). This connects the Arduino signal output to the input leg of the 220-ohm resistor.'",
      "reason": "Why this step matters: e.g. 'This creates the signal path from the Arduino to the resistor, which then limits current before it reaches the LED. Without this, the Arduino has no way to control the LED.'",
      "done": false
    }}
  ],
  "safety_warnings": ["list any safety concerns -- overvoltage, missing resistors on LEDs, short circuits, etc."],
  "improvement_suggestions": ["how to improve this circuit -- add a button, use PWM for dimming, add a second LED, etc."],
  "notes": "additional observations or tips"
}}

CRITICAL RULES:
- NEVER say a circuit is WORKING if there are disconnected wires, missing connections, or unpowered components.
- ALWAYS trace every single wire endpoint. If a wire goes nowhere useful, that is an error.
- You MUST reference SPECIFIC breadboard rows and SPECIFIC MCU pin numbers in every error and fix step.
- The correct_wiring.connections must be a numbered list of physical actions that a BEGINNER can follow step by step.
- Each fix_step must be ONE single physical action (not "fix everything").
- If you cannot determine the circuit type, say "Unknown Circuit" and list what you see.
- If analysis history is provided, acknowledge fixes the user has already made and do NOT repeat them."""

            import google.generativeai as genai
            response = self.model.generate_content(
                [prompt, {"mime_type": "image/jpeg", "data": b64_img}],
                generation_config=genai.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=4096
                )
            )

            text = response.text.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:]) if len(lines) > 1 else text[3:]
            if text.startswith("json"):
                text = text[4:].strip()
            if text.endswith("```"):
                text = text[:-3].strip()

            analysis = json.loads(text)

            # Track resolved issues by diffing with previous
            if self.latest_analysis and self.latest_analysis.get("errors"):
                prev_issues = {e.get("issue", "") for e in self.latest_analysis["errors"]}
                curr_issues = {e.get("issue", "") for e in analysis.get("errors", [])}
                newly_fixed = prev_issues - curr_issues
                for r in newly_fixed:
                    self.completed_steps.add(r[:50])
                fixes_str = "; ".join(r[:30] for r in newly_fixed) if newly_fixed else ""
            else:
                fixes_str = ""

            new_status = analysis.get("status", "UNKNOWN")
            if self._previous_status == "HAS_ERRORS" and new_status == "WORKING":
                print("[VLM] === CIRCUIT FIXED! All errors resolved. ===")
            self._previous_status = new_status
            self._identified_circuit_type = analysis.get("circuit_type", "Unknown")

            self.analysis_count += 1
            analysis["_analysis_id"] = self.analysis_count
            analysis["_timestamp"] = time.strftime("%H:%M:%S")
            analysis["_resolved_count"] = len(self.completed_steps)

            # Store in history for multi-turn memory
            self._analysis_history.append({
                "id": self.analysis_count,
                "time": analysis["_timestamp"],
                "status": new_status,
                "circuit": self._identified_circuit_type,
                "n_errors": len(analysis.get("errors", [])),
                "fixes_applied": fixes_str
            })
            if len(self._analysis_history) > self._max_history * 2:
                self._analysis_history = self._analysis_history[-self._max_history:]

            with self.lock:
                self.latest_analysis = analysis

            n_errors = len(analysis.get("errors", []))
            missed = len(analysis.get("components_yolo_missed", []))
            has_ref = "correct_wiring" in analysis
            print(f"[VLM] #{self.analysis_count}: {self._identified_circuit_type} | {new_status} | {n_errors} errors | {missed} YOLO-missed | ref={'yes' if has_ref else 'no'}")

        except json.JSONDecodeError:
            try:
                text = response.text.strip()
                start = text.find("{")
                end = text.rfind("}") + 1
                if start >= 0 and end > start:
                    analysis = json.loads(text[start:end])
                    self.analysis_count += 1
                    analysis["_analysis_id"] = self.analysis_count
                    analysis["_timestamp"] = time.strftime("%H:%M:%S")
                    analysis["_resolved_count"] = len(self.completed_steps)
                    with self.lock:
                        self.latest_analysis = analysis
                    print(f"[VLM] Salvaged partial #{self.analysis_count}.")
            except Exception:
                pass
        except Exception as e:
            print(f"[VLM] Error: {e}")
            traceback.print_exc()
        finally:
            self._analyzing = False

    def get_latest(self):
        with self.lock:
            return self.latest_analysis
