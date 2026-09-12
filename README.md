# CircuitPulse ⚡
**Real-Time AI Hardware Debugger & Intelligent Circuit Inspector**

CircuitPulse is an edge-deployed computer vision and circuit reasoning engine built for Raspberry Pi 5 and edge devices. It inspects electronic breadboards and microcontroller setups in real time at **30 FPS**, detects wiring errors, validates pin mappings, decodes resistor color bands, and guides makers with actionable AR overlays and voice feedback.

---

## 🌟 Key Features

* **Real-Time 30 FPS Stream & Low-Latency Vision**: Optimized multi-threaded pipeline decoupling video streaming from AI inference.
* **Interactive AR HUD Overlay**: Real-time vector canvas projecting glowing pin targets, breadboard row guides, and floating resistor color-code badges directly on the camera feed.
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

## 📂 Repository Architecture

`
circuitpulse/
├── ar/                          # Augmented Reality Frontend
│   ├── index.html               # Web AR interactive viewport & diagnostics HUD
│   ├── ar_overlay.js            # 60 FPS HTML5 vector AR canvas renderer
│   ├── styles.css               # Futuristic cyberpunk / dark-mode AR styles
│   └── README.md                # AR module documentation
├── backend/                     # REST & Video Streaming Server
│   ├── app.py                   # Flask backend serving AR, stream, detections & logic
│   ├── requirements.txt         # Backend Python dependencies
│   └── README.md                # Backend API documentation
├── engine/                      # Circuit Reasoning & Netlist Verification
│   ├── circuit.py               # Real-time topology reasoning & pin mapping (Pin 8 vs 17)
│   ├── circuit_engine.py        # Engine import alias
│   ├── rules.py                 # Netlist safety and polarity checker
│   ├── netlist_data.py          # Circuit netlist schemas
│   ├── test_engine.py           # Netlist engine verification test cases
│   ├── circuits/                # JSON schemas for circuit validation
│   │   ├── arduino_led.json     # Arduino LED blink & output circuit rules
│   │   ├── voltage_divider.json # Resistor network rules
│   │   └── freeform_safety.json # General short-circuit & safety rules
│   └── README.md                # Engine documentation
├── vision/                      # Computer Vision & Inference Modules
│   ├── resistor.py              # 4-band resistor color-code decoder
│   ├── tracker.py               # Exponential moving average (EMA) box smoother
│   └── README.md                # Vision pipeline documentation
├── pi_transfer/                 # Standalone Raspberry Pi 5 deployment package
│   ├── app.py                   # Integrated Pi vision server
│   ├── circuit.py               # Circuit verification engine
│   ├── resistor.py              # Resistor decoder
│   ├── tracker.py               # Box smoother
│   ├── index.html               # Local HUD interface
│   └── models/                  # Production YOLOv8 weights (.pt)
│       ├── base.pt              # Electronics detector
│       ├── passives.pt          # Wire, resistor, and breadboard model
│       ├── arduino.pt           # Arduino Uno & ATmega328P model (0.989 mAP)
│       └── faults.pt            # PCB hardware defect model
├── test_circuit_engine.py       # Automated 7-rule circuit verification tests
├── train_model.py               # YOLOv8 training script for custom datasets
├── deploy.py                    # Deployment helper script
├── requirements.txt             # Project-wide dependencies
└── README.md                    # Project documentation
`

---

## 🚀 Getting Started

### 1. Requirements
* **Platform**: Raspberry Pi 5 (recommended) / Pi 4 / Windows / Linux
* **Python**: 3.10+
* **Camera**: IP Webcam (Android app) or USB Webcam / Pi Camera Module

### 2. Quick Run (Backend + AR)

`ash
# Clone the repository
git clone https://github.com/saranyachoudhary3/circuitpulse.git
cd circuitpulse

# Install dependencies
pip install -r requirements.txt

# Start backend server
python backend/app.py
`

Open your browser at:
`
http://localhost:5000/
`

### 3. Running on Raspberry Pi 5

`ash
cd pi_transfer
python3 app.py
`

### 4. Running Automated Tests

`ash
# Run circuit engine tests
python test_circuit_engine.py

# Run netlist rules tests
python engine/test_engine.py
`

---

## 📄 License
MIT License. Created for makers, students, and engineers.
