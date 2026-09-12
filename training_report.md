# CircuitPulse - Comprehensive Training Report

**Generated:** 2026-09-11 18:43:24

---

## Model 1: Resistor-Detection--5

- **Classes (3):** breadboard, resistor, wire
- **Training images:** 1596
- **Epochs:** 60
- **Training time:** 16.7 min
- **mAP@50:** 0.7749
- **mAP@50-95:** 0.5787
- **Precision:** 0.8511
- **Recall:** 0.7606
- **Weights:** `C:\Users\Ayushman\Desktop\circuit_pulse\trained_models\circuitpulse_m1_Resistor-Detection--5_best.pt`

---

## Model 2: Component-Detection-Arduino-UNO-1

- **Classes (24):** 16MHz Crystal Oscillator, 16MHz Crystal Oscillator Missing, 5V Regulator, 5V Regulator Missing, ATmega328P MC, ATmega328P MC Missing, CK47Capacitor, CK47Capacitor Missing, Connecting Pins, Connecting Pins Missing, DC Power Port, DC Power Port Missing, LED, LED Missing, LM358, LM358 Missing, Poly Fuse, Poly Fuse Missing, Reset Button, Reset Button Missing, USB Connector, USB Connector Missing, USB-TTL Converter, USB-TTL Converter Missing
- **Training images:** 630
- **Epochs:** 60
- **Training time:** 12.7 min
- **mAP@50:** 0.9922
- **mAP@50-95:** 0.9480
- **Precision:** 0.9802
- **Recall:** 0.9964
- **Weights:** `C:\Users\Ayushman\Desktop\circuit_pulse\trained_models\circuitpulse_m2_Component-Detection-Arduino-UNO-1_best.pt`

---

## Model 3: yolov8-pcb-defects-1

- **Classes (6):** copper, mousebite, open, pin-hole, short, spur
- **Training images:** 350
- **Epochs:** 80
- **Training time:** 5.6 min
- **mAP@50:** 0.8890
- **mAP@50-95:** 0.4800
- **Precision:** 0.9101
- **Recall:** 0.8326
- **Weights:** `C:\Users\Ayushman\Desktop\circuit_pulse\trained_models\circuitpulse_m3_yolov8-pcb-defects-1_best.pt`

---

## Model 4: Electronics-components-1

- **Classes (6):** Capacitor, Diode, LED, Resistor, Transistor, Zener Diode
- **Training images:** 123
- **Epochs:** 80
- **Training time:** 1.5 min
- **mAP@50:** 0.6585
- **mAP@50-95:** 0.2830
- **Precision:** 0.5712
- **Recall:** 0.5860
- **Weights:** `C:\Users\Ayushman\Desktop\circuit_pulse\trained_models\circuitpulse_m4_Electronics-components-1_best.pt`

---

## Deployment - Raspberry Pi

```bash
# Copy all models to Pi
scp trained_models/*.pt <user>@<pi-ip>:~/circuitpulse/models/
```

```python
from ultralytics import YOLO
import glob

# Load all models
models = [YOLO(p) for p in glob.glob('models/*_best.pt')]

# Run inference with all models
for model in models:
    results = model.predict(frame, conf=0.25)
```
