# CircuitPulse: Complete System Architecture & Humanization Specification

> **Notice for the Refactoring Agent**:
> This document provides the complete architectural breakdown, runtime logic, file inventory, and explicit guidelines required to **humanize** the CircuitPulse codebase. 
> Your objective is to strip all AI hallmarks, watermarks, decorative comment banners, emojis, and bot-generated boilerplate while **strictly preserving 100% runtime stability, network endpoints, hardware interfaces, and API contracts**.

---

## 1. Project Overview & Operational Context

**CircuitPulse** is an edge-deployed real-time electronic circuit inspection and fault detection system.
- **Compute Unit**: Raspberry Pi 5 (4GB RAM) running Linux (Debian aarch64).
- **Camera Input**: Android Smartphone running IP Webcam app streaming MJPEG over Wi-Fi (`http://192.0.0.4:8080/video`).
- **Hardware Peripherals**: Arduino Uno connected to the Pi via USB Serial (`/dev/ttyACM0`) managed with `arduino-cli`.
- **Inference Engine**: Ultralytics YOLOv8 running PyTorch models (`.pt`) on the Pi CPU with multithreading and parallel execution.
- **Client / Interface**: Web Dashboard running on a remote laptop browser over LAN (`http://<PI_IP>:5000/dashboard`), delivering:
  - Low-latency live video stream with annotated bounding boxes.
  - Browser-synthesized Text-to-Speech (TTS) alerts with spatial audio localization ("top-left", "bottom-right", etc.).
  - Synthetic Web Audio API buzzer tone prior to voice alerts.
  - Mode controls to dynamically switch detection modes.

---

## 2. File Inventory & Component Directory

```
circuit_pulse/
 deploy.py                         # Automation script for deploying updates from laptop to Pi
 PROJECT_OVERVIEW_HUMANIZE_PROMPT.md # (This documentation file)
 pi_transfer/                      # Primary folder deployed to ~/circuitpulse on the Pi
     server_v2.py                  # Core backend: Flask server, camera grabber, parallel YOLO
     server.py                     # Legacy single-threaded server (reference only)
     dashboard.html                # Frontend: Video feed, polling, TTS, buzzer, controls
     models/                       # Trained YOLOv8 weights (.pt)
         PRODUCTION_eesob_48class_best.pt                    # 48 classes: boards, sensors, modules
         circuitpulse_m4_Electronics-components-1_best.pt    # 6 classes: resistor, LED, capacitor, diode, transistor, zener
         PRODUCTION_pcb_faults_best.pt                       # 6 classes: short, open, spur, mousebite, pin-hole, copper
         circuitpulse_m1_Resistor-Detection--5_best.pt       # 3 classes: breadboard, resistor, wire
         circuitpulse_m2_Component-Detection-Arduino-UNO-1_best.pt # 24 classes: Arduino components & missing items
```

---

## 3. Deep Architectural & Logic Breakdown

### A. Backend Architecture (`server_v2.py`)

1. **Dual Parallel Model Execution (Default "All" Mode)**:
   - To catch both large modules (breadboard, Arduino, sensors) and small electronic passives (resistors, LEDs, diodes) at the same time, the server runs **two separate models concurrently** per frame:
     - `model_main`: EESOB dataset (48 classes)
     - `model_electronics`: Electronics dataset (6 classes)
   - Executed via `concurrent.futures.ThreadPoolExecutor(max_workers=2)` so both CPU cores on the Pi 5 compute in parallel, slashing per-frame inference latency from ~600ms to ~350ms.
2. **IoU Deduplication (`deduplicate_detections`)**:
   - Merges detections from both models.
   - Calculates Intersection over Union (IoU) between bounding boxes.
   - If two detected boxes overlap with an IoU > `IOU_THRESHOLD` (0.45), the system discards the duplicate and retains the detection with the higher confidence score.
3. **False Positive & Noise Filtering (`filter_box`)**:
   - `CONF_THRESHOLD = 0.60`: Strict confidence to eliminate background phantom detections and misrecognitions of daily objects (e.g., eyeglasses, laptop keyboard).
   - `MIN_BOX_AREA = 500`: Discards tiny artifact boxes (< 500 px).
   - `MAX_BOX_RATIO = 0.65`: Discards overly massive bounding boxes covering >65% of the frame (which occur when the model mistakes a laptop lid or background for an Arduino board).
4. **Threaded Camera Stream & Frame Dropping (`camera_thread`)**:
   - Uses `cv2.VideoCapture` with `CAP_PROP_BUFFERSIZE = 1`.
   - Incoming frames (typically 1080p from IP Webcam) are scaled down to `FRAME_WIDTH = 640` to avoid overwhelming memory and CPU.
   - Operates with a single-frame buffer protected by `threading.Lock()`. New frames continuously overwrite old ones; stale queued frames are dropped immediately to eliminate latency accumulation.
5. **Streaming & REST Endpoints**:
   - `GET /api/stream`: Multipart MJPEG stream (`multipart/x-mixed-replace; boundary=frame`) encoded at JPEG quality 65, serving ~20 FPS.
   - `GET /api/latest`: Returns JSON payload of the latest detection set, active mode, timestamp, camera connectivity status, and measured FPS.
   - `POST /api/mode`: Dynamically loads models (switches between dual "all" mode and single on-demand modes like "faults", "resistors", "arduino").
   - `POST /api/detect`: Accepts static image uploads (file multipart or base64) for on-demand inspection.
   - `GET /api/history`: Returns scan history log.
   - `GET /api/status`: Health check endpoint.
   - `GET /dashboard`: Serves `dashboard.html`.

---

### B. Frontend Architecture (`dashboard.html`)

1. **Video Streaming & Auto-Recovery**:
   - Directly renders `<img id="videoFeed" src="/api/stream" />`.
   - Features automatic reload and timestamp-busting reconnection logic if the stream disconnects.
2. **State Polling**:
   - Queries `/api/latest` every 600ms via `setInterval` to fetch the real-time detection array.
   - Updates FPS badge, connection indicators, and detected object count.
3. **Voice Alerts & Spatial Localization**:
   - Utilizes the browser's native `window.speechSynthesis` (Web Speech API) so alerts output through the client's laptop speakers.
   - **Spatial Mapper (`getLocation`)**: Divides the camera canvas into a 3x3 quadrant grid based on the bounding box center `(cx, cy)`:
     - Returns locations like `"at the top left"`, `"on the right side"`, `"in the center"`, etc.
   - **Fault Detection (`isFault`)**: Inspects class names against fault substrings (`short`, `open`, `spur`, `missing`, `defect`, etc.).
   - **Spam Cooldown (`COOLDOWN_MS = 8000`)**: Caches spoken alerts in a Map with timestamps; identical alert texts are silenced for 8 seconds.
4. **Hardware-Emulated Audio Buzzer**:
   - Uses the browser's native `window.AudioContext` (Web Audio API) to synthesize an 880 Hz square-wave beep for 150ms at gain 0.12 immediately before speech synthesis fires.

---

## 4. Specific "AI Hallmarks" & Watermarks to Eliminate

When humanizing the codebase, the refactoring agent must scrub all stylistic giveaways typical of LLM generation:

1. **Box & Unicode Divider Banners**:
   - Replace or eliminate:
     ```python
     # 
     # CONFIGURATION
     # 
     #  Global State 
     ```
     With clean, standard developer sectioning (or standard PEP-8 spacing).
2. **Over-explanatory & Academic Comments**:
   - Remove obvious comments explaining basic syntax (e.g., `# Run YOLO detection`, `# Return past detection results`, `# Start camera thread`).
   - Retain only practical, technical comments (e.g., explaining why `CAP_PROP_BUFFERSIZE` is set to 1, or why image width is capped at 640).
3. **Clich Emojis in UI & Code**:
   - Remove emojis from logs and UI buttons (` CircuitPulse`, ` Components`, ` Faults`, ` Resistors`, ` Arduino`, ` Voice Alerts`).
   - Replace with clean, professional text or standard SVG/CSS icons.
4. **Robotic Logging Strings**:
   - Clean up print statements like `"  OK - 48 classes loaded"` or `"=================================================="`.
   - Use standard Python `logging` or concise, realistic CLI output.
5. **AI Docstring Boilerplate**:
   - Replace repetitive "Usage:", "CircuitPulse v2 - Optimized Backend Server" docstrings with standard, clean module docstrings.

---

## 5. Strict Refactoring Guardrails & Constraints

The refactoring agent **MUST NOT** break any of the following functional requirements:

1. **API Contracts Must Remain Identical**:
   - Do NOT rename keys in JSON responses (`mode`, `timestamp`, `num_detections`, `detections`, `camera_connected`, `fps`, `bbox`, `x1`, `y1`, `x2`, `y2`, `class`, `confidence`). The dashboard depends on these exact keys.
2. **Model Paths & Formats**:
   - Keep `.pt` PyTorch model loading via Ultralytics `YOLO(...)`.
   - Do NOT convert back to NCNN or ONNX unless explicitly verified with dynamic shape support (fixed 640x640 tensor shapes broke previous builds).
3. **Image Size Constraint**:
   - `IMG_SIZE` MUST remain `640`. Downscaling YOLO input below 640 (e.g., 320 or 256) causes the models to completely miss resistors, wires, and small passive components.
4. **Camera Resolution & Buffer**:
   - Keep camera frame resizing (`FRAME_WIDTH = 640`) and buffer size 1. This is the primary mechanism that prevents video jitter and queue lag on the Raspberry Pi 5.
5. **Hardware Serial Link**:
   - Do not remove or alter Arduino serial communications (`/dev/ttyACM0`) or Arduino Uno compilation commands if present.
6. **TTS & Audio Compatibility**:
   - Keep `speechSynthesis` and Web Audio API synthesized tones intact in `dashboard.html`. They allow the user's laptop to serve as the speaker since the Pi has no built-in audio output.

---

## 6. Prompt to Give the Refactoring / Humanizing Agent

*Copy and paste the following prompt into your target AI agent along with the code files:*

```text
You are a senior embedded systems and full-stack software engineer. 
Your task is to refactor and "humanize" the provided code files (`server_v2.py`, `dashboard.html`, and `deploy.py`) according to the architectural specification in `PROJECT_OVERVIEW_HUMANIZE_PROMPT.md`.

Objectives:
1. Strip all AI watermarks, decorative unicode boxes (e.g. , ), unnecessary emojis, and boilerplate robotic comments.
2. Make the code look like it was authored by an experienced, practical developer building an embedded computer vision project.
3. Clean up the naming conventions, indentation, and structure to follow idiomatic Python (PEP 8) and clean modern JavaScript/HTML/CSS.
4. CRITICAL: Maintain 100% functional equivalence. Do not change REST API endpoint paths, JSON response schemas, YOLO inference resolutions (640x640), thread synchronization logic, or frontend DOM element IDs.
5. Provide the complete, drop-in replacement code for each file.
```
