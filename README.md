# CircuitPulse ⚡
**Real-Time AI Hardware Debugger & Intelligent Circuit Inspector**

CircuitPulse is an edge-deployed computer vision and circuit reasoning engine built for Raspberry Pi 5 and edge devices. It inspects electronic breadboards and microcontroller setups in real time at **30 FPS**, detects wiring errors, validates pin mappings, decodes resistor color bands, and guides makers with actionable voice and visual feedback.

---

## 🌟 Key Features

* **Real-Time 30 FPS Stream & Low-Latency Vision**: Optimized multi-threaded pipeline decoupling video streaming from AI inference.
* **Intelligent Circuit Verification**:
  * **Pin Mappings**: Automatically identifies misplaced jumper cables (e.g., *Wire connected to Arduino Pin 8 instead of Pin 17*).
  * **Breadboard Row Alignment**: Verifies component and wire pinholes on breadboard rows (e.g., *Wire in Row 8 must be moved to Row 17*).
  * **Critical Short-Circuit Protection**: Detects direct bridges between 5V power rails and Ground (GND).
  * **Component Protection**: Warns against unprotected LEDs missing current-limiting resistors (e.g., *requires 220Ω in series*).
* **Two-Tier Inspection (Afar vs Close-Up)**:
  * **Overview Distance (Afar)**: Analyzes complete circuit topology, microcontroller, boards, wires, and power rails at a glance.
  * **Macro Mode (Close-Up)**: Automatically zooms in on resistors to extract color bands (e.g., Red-Red-Brown-Gold) and compute resistance (220Ω ±5%).
* **Microcontroller / Microprocessor Identification**: Detects and displays chips such as **ATmega328P** (Arduino Uno/Nano), **ATmega2560** (Mega), and **ESP32 Dual-Core**.
* **Temporal State Stability**: 15-second state memory prevents the system from confusing circuit outcomes when bringing the camera close to inspect individual components.
* **Auditory Feedback (TTS)**: Spoken voice guidance via espeak-ng on Raspberry Pi and Web Speech API in the browser.

---

## 📂 Repository Structure

`
circuitpulse/
├── pi_transfer/                 # Raspberry Pi deployment bundle
│   ├── app.py                   # Main Flask video streaming & inference server
│   ├── circuit.py               # Circuit verification engine & pin topology logic
│   ├── circuit_engine.py        # Module alias for circuit engine
│   ├── tracker.py               # Exponential moving average (EMA) bounding box smoother
│   ├── resistor.py              # Computer vision resistor color band decoder
│   ├── index.html               # Web interface & live HUD stream
│   ├── circuits/                # JSON schemas for circuit verification
│   │   ├── arduino_led.json     # Arduino LED blink & output circuit rules
│   │   ├── voltage_divider.json # Resistor network rules
│   │   └── freeform_safety.json # General short-circuit & safety rules
│   └── models/                  # Production YOLOv8 weights (PyTorch .pt)
│       ├── base.pt              # 48-class electronics model
│       ├── passives.pt          # High-precision wire, resistor, and breadboard model
│       ├── arduino.pt           # Arduino Uno & ATmega328P component model (0.989 mAP)
│       └── faults.pt            # PCB hardware defect model
├── test_circuit_engine.py       # Unit tests verifying all 7 circuit rules
├── train_model.py               # YOLOv8 training script for custom datasets
├── deploy.py                    # Deployment helper script
├── requirements.txt             # Python dependencies
└── README.md                    # Documentation
`

---

## 🚀 Getting Started

### 1. Requirements
* **Platform**: Raspberry Pi 5 (recommended) / Pi 4 / Windows / Linux
* **Python**: 3.10+
* **Camera**: IP Webcam (Android app) or USB Webcam / Pi Camera Module

### 2. Installation on Raspberry Pi

`ash
# Clone the repository
git clone https://github.com/saranyachoudhary3/circuitpulse.git
cd circuitpulse

# Create Python virtual environment
python3 -m venv ~/circuitpulse_env --system-site-packages
source ~/circuitpulse_env/bin/activate

# Install system dependencies
sudo apt update
sudo apt install -y python3-opencv espeak-ng ffmpeg libopenblas-dev

# Install Python packages
pip install -r requirements.txt
`

### 3. Running the Vision Server

`ash
cd pi_transfer
python3 app.py
`

Open your browser and navigate to:
`
http://<your-pi-ip>:5000
`

### 4. Running as a Background System Service (systemd)

To make CircuitPulse run automatically on boot:

`ash
sudo tee /etc/systemd/system/circuitpulse.service > /dev/null <<EOF
[Unit]
Description=CircuitPulse Vision Server
After=network.target

[Service]
WorkingDirectory=/home//circuitpulse/pi_transfer
ExecStart=/home//circuitpulse_env/bin/python3 /home//circuitpulse/pi_transfer/app.py
Restart=always
RestartSec=5
User=
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable circuitpulse
sudo systemctl start circuitpulse
`

---

## 🧪 Testing Circuit Rules

Run the automated test suite verifying all 7 circuit rules:

`ash
python test_circuit_engine.py
`

Expected output:
`
Testing 100% Automatic Circuit Logic & Verification Engine...
Test 1 (Auto-Detected Valid Circuit): PASS
Test 2 (Wire in Pin 7, Expected at Pin 15): FAULT_DETECTED
Test 3 (Wire Corrected from Pin 7 to Pin 15): PASS
Test 4 (Missing Resistor): FAULT_DETECTED
Test 5 (Pin 8 Mismatch): FAULT_DETECTED
Test 6 (Auto-Detected Critical Short Circuit): FAULT_DETECTED
Test 7 (Auto-Detected Incorrect Resistor Value): FAULT_DETECTED
[ALL 7 AUTOMATIC DETECTION TESTS PASSED SUCCESSFULLY]
`

---

## 📡 API Endpoints

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| / | GET | Live web dashboard and HUD |
| /api/stream | GET | MJPEG video stream with bounding boxes & HUD overlay |
| /api/detections | GET | Real-time JSON list of detected objects, confidences, and bounding boxes |
| /api/verification | GET | Current circuit report: status (PASS/FAULT), errors, remedies, and TTS |
| /api/circuits | GET | List of available presets and auto-detected circuit identity |
| /api/decode-resistor | POST | Trigger high-resolution crop color-code decoding on demand |

---

## 📄 License
MIT License. Created for makers, students, and engineers.
