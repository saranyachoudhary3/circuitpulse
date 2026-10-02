from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

doc = Document()

#  Styles 
style = doc.styles['Normal']
font = style.font
font.name = 'Calibri'
font.size = Pt(11)

# 
# TITLE PAGE
# 
for _ in range(6):
    doc.add_paragraph()

title = doc.add_paragraph()
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = title.add_run('CircuitPulse')
run.bold = True
run.font.size = Pt(36)
run.font.color.rgb = RGBColor(0, 102, 204)

subtitle = doc.add_paragraph()
subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = subtitle.add_run('AI-Powered Real-Time Circuit Inspection System')
run.font.size = Pt(18)
run.font.color.rgb = RGBColor(80, 80, 80)

doc.add_paragraph()

tagline = doc.add_paragraph()
tagline.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = tagline.add_run('Detect. Diagnose. Debug.')
run.italic = True
run.font.size = Pt(14)
run.font.color.rgb = RGBColor(120, 120, 120)

for _ in range(6):
    doc.add_paragraph()

info = doc.add_paragraph()
info.alignment = WD_ALIGN_PARAGRAPH.CENTER
info.add_run('Project Documentation\n').font.size = Pt(12)
info.add_run('Version 1.0 | September 2026').font.size = Pt(11)

doc.add_page_break()

# 
# TABLE OF CONTENTS
# 
doc.add_heading('Table of Contents', level=1)
toc_items = [
    '1. Executive Summary',
    '2. What is CircuitPulse?',
    '3. Key Features & Functionalities',
    '4. System Architecture',
    '5. AI Models & Detection Capabilities',
    '6. Hardware Requirements',
    '7. How It Works  Step by Step',
    '8. Use Cases',
    '9. Technical Specifications',
    '10. Future Scope',
]
for item in toc_items:
    p = doc.add_paragraph(item)
    p.paragraph_format.space_after = Pt(4)

doc.add_page_break()

# 
# 1. EXECUTIVE SUMMARY
# 
doc.add_heading('1. Executive Summary', level=1)
doc.add_paragraph(
    'CircuitPulse is an AI-powered real-time circuit inspection system designed to help electronics '
    'students, hobbyists, and engineers detect component placement errors, wiring faults, and missing '
    'parts on breadboard circuits using just a smartphone camera and a Raspberry Pi 5. It leverages '
    'state-of-the-art YOLOv8 deep learning models trained on over 10,000 annotated images to identify '
    '48 different electronic components and 6 types of circuit faults  all in real-time, at the edge, '
    'without requiring any cloud connectivity.'
)
doc.add_paragraph(
    'The system is lightweight (each AI model is only 6 MB), fast (capable of real-time inference), '
    'and affordable (runs on a $60 Raspberry Pi 5 with a smartphone as the camera). It is designed '
    'to be a teaching aid, a debugging tool, and a quality assurance system for electronics prototyping.'
)

# 
# 2. WHAT IS CIRCUITPULSE?
# 
doc.add_heading('2. What is CircuitPulse?', level=1)
doc.add_paragraph(
    'CircuitPulse is a computer vision system that watches a physical breadboard circuit through a '
    'camera and intelligently identifies:'
)

bullets = [
    'What components are present (resistors, LEDs, capacitors, Arduino boards, sensors, etc.)',
    'Whether any components are missing from the circuit',
    'Whether there are wiring faults such as short circuits, open circuits, or reversed polarity',
    'The type and location of each detected component or fault',
]
for b in bullets:
    doc.add_paragraph(b, style='List Bullet')

doc.add_paragraph(
    'Think of it as a "spell checker" for circuits  just as a spell checker highlights misspelled '
    'words in a document, CircuitPulse highlights incorrect or missing components in your circuit.'
)

# 
# 3. KEY FEATURES & FUNCTIONALITIES
# 
doc.add_heading('3. Key Features & Functionalities', level=1)

# Feature 1
doc.add_heading('3.1 Real-Time Component Detection (48 Classes)', level=2)
doc.add_paragraph(
    'CircuitPulse can identify 48 different types of electronic components in real-time from a live '
    'camera feed. The AI draws bounding boxes around each detected component and labels it with its name '
    'and confidence score.'
)
doc.add_paragraph('Detectable components include:')
components = [
    'Microcontrollers: Arduino Uno, Arduino Nano, Arduino Mega, Arduino Mini, ESP32, ESP WiFi, Lilypad',
    'Passive Components: Resistors, Capacitors, Potentiometers, Inductors',
    'Active Components: LEDs, LED Matrices, 7-Segment Displays, LCD, OLED LCD, Diodes, Transistors',
    'Sensors: Ultrasonic, PIR, IR Sensor, IR Receiver, DHT (Temperature/Humidity), Flame Sensor, '
    'LDR (Light), Soil Moisture, Gas Sensor, Sound Sensor',
    'Motors & Actuators: DC Motor, Servo Motor, Stepper Motor, Stepper Driver, Fan, Buzzer, Speaker',
    'Communication Modules: Bluetooth, RFID, RTC (Real-Time Clock)',
    'Power Components: Battery (9V), LiPo Battery, Solar Panel, Power Module, Battery Holder',
    'Structural: Breadboard, Prototype PCB, H-Bridge, Relay, Joystick, Keypad, Button, Switch',
]
for c in components:
    doc.add_paragraph(c, style='List Bullet')

# Feature 2
doc.add_heading('3.2 Circuit Fault Detection (6 Fault Types)', level=2)
doc.add_paragraph(
    'CircuitPulse includes a dedicated fault detection model that can identify 6 common types of '
    'circuit board defects:'
)
faults = [
    'Short Circuit  Unintended connection between two conductors',
    'Open Circuit  A break in the circuit path where current cannot flow',
    'Mouse Bite  Irregular edges or nibbles on traces',
    'Pin Hole  Small holes in copper traces or solder joints',
    'Spur  Unwanted protrusion of copper from a trace',
    'Copper Defect  Missing or excess copper on the board',
]
for f in faults:
    doc.add_paragraph(f, style='List Bullet')

# Feature 3
doc.add_heading('3.3 Missing Component Detection', level=2)
doc.add_paragraph(
    'A specialized model detects whether critical components are present or missing from an Arduino '
    'circuit. It recognizes 24 classes  12 component types and their corresponding "Missing" variants:'
)
missing = [
    'Arduino Board / Arduino Board Missing',
    'Crystal Oscillator / Crystal Oscillator Missing',
    'Electrolytic Capacitor / Electrolytic Capacitor Missing',
    'LED Indicator / LED Indicator Missing',
    'Poly Fuse / Poly Fuse Missing',
    'Reset Button / Reset Button Missing',
    'USB Connector / USB Connector Missing',
    'USB-TTL Converter / USB-TTL Converter Missing',
    'Voltage Regulator / Voltage Regulator Missing',
    'And more...',
]
for m in missing:
    doc.add_paragraph(m, style='List Bullet')
doc.add_paragraph(
    'This model achieved an exceptional mAP@50 of 0.99+ during validation, meaning it is extremely '
    'accurate at telling you what is missing from your circuit.'
)

# Feature 4
doc.add_heading('3.4 Multi-Mode Switching', level=2)
doc.add_paragraph(
    'Users can switch between detection modes in real-time using keyboard shortcuts:'
)
table = doc.add_table(rows=4, cols=2)
table.style = 'Light Grid Accent 1'
table.alignment = WD_TABLE_ALIGNMENT.CENTER
hdr = table.rows[0].cells
hdr[0].text = 'Key'
hdr[1].text = 'Mode'
row1 = table.rows[1].cells
row1[0].text = 'Press "1"'
row1[1].text = 'Component Detection  Identifies all 48 component types'
row2 = table.rows[2].cells
row2[0].text = 'Press "2"'
row2[1].text = 'Fault Detection  Highlights shorts, opens, and defects'
row3 = table.rows[3].cells
row3[0].text = 'Press "3"'
row3[1].text = 'Missing Parts  Shows which components are absent'

# Feature 5
doc.add_heading('3.5 Edge Computing (No Internet Required)', level=2)
doc.add_paragraph(
    'CircuitPulse runs entirely on the Raspberry Pi 5  no cloud connection, no API calls, no '
    'internet needed after initial setup. All AI inference happens locally on the device, ensuring '
    'low latency, data privacy, and offline operation. This makes it ideal for classrooms, workshops, '
    'and field environments with limited connectivity.'
)

# Feature 6
doc.add_heading('3.6 Smartphone Camera Integration', level=2)
doc.add_paragraph(
    'Instead of requiring an expensive dedicated camera, CircuitPulse uses your existing smartphone '
    'as a wireless camera via the free "IP Webcam" (Android) or "DroidCam" (iOS) apps. The phone '
    'streams its camera feed over Wi-Fi, and the Pi processes each frame with the AI model. '
    'This provides high-resolution image input at zero additional hardware cost.'
)

# Feature 7
doc.add_heading('3.7 Lightweight & Portable', level=2)
doc.add_paragraph(
    'Each trained AI model is only 6 MB in size, and the entire system (all 6 models + scripts) '
    'weighs under 36 MB. The Raspberry Pi 5 is credit-card-sized and battery-powerable. This makes '
    'the entire setup highly portable  you can carry it in a pencil case and set it up anywhere '
    'in under 5 minutes.'
)

# 
# 4. SYSTEM ARCHITECTURE
# 
doc.add_heading('4. System Architecture', level=1)
doc.add_paragraph('The CircuitPulse system consists of three main components:')

doc.add_heading('4.1 The Eye  Smartphone Camera', level=2)
doc.add_paragraph(
    'A smartphone running the IP Webcam app is mounted above the breadboard circuit. It captures '
    'live video and streams it over Wi-Fi to the Raspberry Pi. The phone acts purely as a video '
    'source  all processing is done on the Pi.'
)

doc.add_heading('4.2 The Brain  Raspberry Pi 5', level=2)
doc.add_paragraph(
    'The Raspberry Pi 5 (4GB RAM) receives the video stream, runs the YOLOv8 AI models on each '
    'frame, and displays the annotated output on a connected monitor or via Pi Connect remote desktop. '
    'It uses the quad-core ARM Cortex-A76 processor for inference at approximately 3-5 FPS.'
)

doc.add_heading('4.3 The Target  Arduino + Breadboard Circuit', level=2)
doc.add_paragraph(
    'The physical circuit built on a breadboard with an Arduino Uno and various components (LEDs, '
    'resistors, sensors, etc.) is the subject being inspected. The Arduino is powered via USB from '
    'the Pi, creating a self-contained system.'
)

doc.add_paragraph('Data Flow:')
doc.add_paragraph('Phone Camera  Wi-Fi Stream  Raspberry Pi  YOLOv8 AI  Annotated Display')

# 
# 5. AI MODELS & DETECTION CAPABILITIES
# 
doc.add_heading('5. AI Models & Detection Capabilities', level=1)
doc.add_paragraph(
    'CircuitPulse ships with 6 purpose-trained YOLOv8n (nano) models, each optimized for a specific '
    'detection task:'
)

table2 = doc.add_table(rows=7, cols=4)
table2.style = 'Light Grid Accent 1'
table2.alignment = WD_TABLE_ALIGNMENT.CENTER
headers = table2.rows[0].cells
headers[0].text = 'Model'
headers[1].text = 'Classes'
headers[2].text = 'Training Images'
headers[3].text = 'Purpose'

models_data = [
    ['PRODUCTION_eesob_48class', '48', '8,322', 'Primary component detection  Arduino, breadboard, sensors, motors, displays, wireless modules'],
    ['PRODUCTION_pcb_faults', '6', '500', 'Fault detection  shorts, opens, pin-holes, mouse bites, spurs'],
    ['circuitpulse_m2_Arduino', '24', '630', 'Missing component detection  detects present vs. missing parts (0.99+ mAP)'],
    ['circuitpulse_m1_Resistor', '3', '1,596', 'Focused detection of breadboard, resistor, and wire'],
    ['circuitpulse_m3_PCB_Defects', '6', '350', 'PCB-specific defect detection'],
    ['circuitpulse_m4_Electronics', '6', '123', 'Basic components: LED, Capacitor, Diode, Transistor, Zener Diode'],
]
for i, row_data in enumerate(models_data):
    row = table2.rows[i + 1].cells
    for j, val in enumerate(row_data):
        row[j].text = val

doc.add_paragraph()
doc.add_paragraph(
    'All models are based on the YOLOv8n (nano) architecture  the smallest and fastest variant '
    'of YOLOv8, specifically designed for edge devices like the Raspberry Pi. Each model file is '
    'approximately 6 MB in size.'
)

doc.add_heading('5.1 Training Details', level=2)
doc.add_paragraph(
    'Models were trained on an NVIDIA GeForce RTX 5050 Laptop GPU (8 GB VRAM) using the Ultralytics '
    'YOLOv8 framework. Training utilized mixed-precision (AMP) for maximum GPU throughput with '
    'batch sizes up to 64, disk caching, and extensive data augmentation (mosaic, mixup, HSV shifts, '
    'rotation, scaling, and horizontal flip) to ensure robustness to real-world conditions such as '
    'varying lighting, camera angles, and distances.'
)

# 
# 6. HARDWARE REQUIREMENTS
# 
doc.add_heading('6. Hardware Requirements', level=1)

table3 = doc.add_table(rows=8, cols=3)
table3.style = 'Light Grid Accent 1'
table3.alignment = WD_TABLE_ALIGNMENT.CENTER
h = table3.rows[0].cells
h[0].text = 'Component'
h[1].text = 'Specification'
h[2].text = 'Purpose'

hw_data = [
    ['Raspberry Pi 5', '4GB RAM (minimum)', 'AI processing & system controller'],
    ['MicroSD Card', '64GB+, Class 10/A2', 'OS and model storage'],
    ['Power Supply', 'USB-C, 5V/5A', 'Powers the Pi 5'],
    ['Smartphone', 'Android or iOS with camera', 'Wireless camera for circuit inspection'],
    ['Arduino Uno', 'Any version', 'Target circuit microcontroller'],
    ['Breadboard', 'Full-size (830 tie points)', 'Component mounting platform'],
    ['Active Cooling', 'Fan or heatsink case', 'Prevents thermal throttling during AI inference'],
]
for i, row_data in enumerate(hw_data):
    row = table3.rows[i + 1].cells
    for j, val in enumerate(row_data):
        row[j].text = val

# 
# 7. HOW IT WORKS
# 
doc.add_heading('7. How It Works  Step by Step', level=1)

steps = [
    ('Step 1: Build the Circuit', 
     'Assemble your target circuit on the breadboard  LEDs, resistors, jumper wires, and Arduino.'),
    ('Step 2: Mount the Camera', 
     'Place your smartphone above the breadboard (20-30 cm height) pointing down at the circuit. '
     'Start the IP Webcam app to begin streaming.'),
    ('Step 3: Launch CircuitPulse', 
     'On the Raspberry Pi, run "python3 inspect.py" to start the AI inspection system.'),
    ('Step 4: Real-Time Detection', 
     'The system captures each video frame from the phone, passes it through the YOLOv8 model, '
     'and draws labeled bounding boxes around every detected component or fault.'),
    ('Step 5: Switch Modes', 
     'Press "1" for component detection, "2" for fault detection, or "3" for missing parts. '
     'The AI model switches instantly.'),
    ('Step 6: Iterate', 
     'Fix the issues detected by the AI, then re-inspect. The system provides continuous feedback '
     'as you modify your circuit.'),
]
for title, desc in steps:
    doc.add_heading(title, level=2)
    doc.add_paragraph(desc)

# 
# 8. USE CASES
# 
doc.add_heading('8. Use Cases', level=1)

use_cases = [
    ('Education & Classrooms',
     'Teachers can use CircuitPulse to help students verify their breadboard circuits before powering '
     'them on. The AI provides instant feedback on missing or misplaced components, reducing the risk '
     'of damage and accelerating learning.'),
    ('Electronics Hobbyists',
     'Makers and hobbyists can use CircuitPulse as a debugging assistant  point the camera at a '
     'malfunctioning circuit and let the AI identify what might be wrong.'),
    ('Quality Assurance',
     'Small electronics workshops can use CircuitPulse for automated visual inspection of assembled '
     'boards before shipping, catching defects like shorts and missing components.'),
    ('Hackathons & Competitions',
     'Rapid circuit validation during time-constrained events  verify your circuit in seconds instead '
     'of manually tracing every wire.'),
    ('Remote Learning',
     'Instructors can inspect students\' circuits remotely via a camera feed, with the AI providing '
     'objective component identification and fault flagging.'),
]
for title, desc in use_cases:
    doc.add_heading(title, level=2)
    doc.add_paragraph(desc)

# 
# 9. TECHNICAL SPECIFICATIONS
# 
doc.add_heading('9. Technical Specifications', level=1)

table4 = doc.add_table(rows=11, cols=2)
table4.style = 'Light Grid Accent 1'
table4.alignment = WD_TABLE_ALIGNMENT.CENTER
specs = [
    ['AI Framework', 'Ultralytics YOLOv8 (v8.4.147)'],
    ['Model Architecture', 'YOLOv8n (nano)  3.0M parameters, 8.1 GFLOPs'],
    ['Model File Size', '~6 MB per model'],
    ['Input Resolution', '640 x 640 pixels'],
    ['Inference Speed (Pi 5)', '~3-5 FPS (CPU), ~200ms per frame'],
    ['Inference Speed (Laptop GPU)', '~30+ FPS (CUDA GPU)'],
    ['Total Models', '6 specialized detection models'],
    ['Total Component Classes', '48 (EESOB model)'],
    ['Total Fault Classes', '6 (PCB fault model)'],
    ['Training Dataset Size', '10,000+ annotated images across all models'],
]
h = table4.rows[0].cells
h[0].text = 'Specification'
h[1].text = 'Value'
for i, (spec, val) in enumerate(specs):
    row = table4.rows[i + 1].cells
    row[0].text = spec
    row[1].text = val

# 
# 10. FUTURE SCOPE
# 
doc.add_heading('10. Future Scope', level=1)

future = [
    ('Schematic Comparison', 
     'Upload a circuit schematic and have the AI compare the physical circuit against the expected '
     'design, automatically flagging discrepancies.'),
    ('Voice Alerts', 
     'Audio feedback when faults are detected  "Warning: Missing resistor on row 15."'),
    ('Web Dashboard', 
     'A browser-based dashboard accessible from any device on the network, showing live detection '
     'results, detection history, and analytics.'),
    ('Model Expansion', 
     'Train on additional component types (FPGAs, relay modules, motor drivers) and fault categories '
     '(cold solder joints, bridged solder) as datasets become available.'),
    ('ONNX/TensorRT Export', 
     'Export models to optimized inference formats for 2-3x faster performance on the Pi.'),
    ('Mobile App', 
     'A standalone Android/iOS app that runs the AI model directly on the phone, eliminating the '
     'need for a Raspberry Pi entirely.'),
]
for title, desc in future:
    doc.add_heading(title, level=2)
    doc.add_paragraph(desc)

#  Save 
output_path = r"C:\Users\Ayushman\Desktop\CircuitPulse_Documentation.docx"
doc.save(output_path)
print(f"DOCX created: {output_path}")
