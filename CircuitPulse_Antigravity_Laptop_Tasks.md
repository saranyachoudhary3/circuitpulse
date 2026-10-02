# CircuitPulse  Laptop Task Brief (for Antigravity agent)

## 0. Context  read this first

This is a hackathon project called **CircuitPulse**: a Raspberry Pi 5 + camera
system that watches a physical Arduino breadboard circuit and flags wiring
faults (reversed LED polarity, missing resistor, shorts) in a live browser
dashboard. Full architecture and build guide already exists as a PDF
(`CircuitPulse_Execution_Guide.pdf`)  that document owns the Raspberry Pi
side (vision pipeline, rule engine, dashboard server) and the physical
breadboard wiring. **This file only covers the laptop-side work**: getting a
labeled dataset and training a YOLOv8 object-detection model that the Pi can
later load for inference.

Do not touch or assume access to the Raspberry Pi in this session  just
produce a trained model file (`best.pt`) plus a short results summary that a
human will copy over to the Pi afterward (`scp best.pt user@<pi-ip>:~/circuitpulse/`).

**Time budget: this is one slice of a 12-hour hackathon.** Target finishing
the objective below in under 60 minutes of wall-clock time, training
included. If anything stalls for more than ~10 minutes (dataset auth,
dependency conflicts, etc.), fall back to the smallest viable version
(fewer epochs, smaller dataset) rather than debugging indefinitely  a
working nano model with mediocre accuracy is more useful right now than a
perfect model that isn't finished in time.

---

## 1. Objective

Produce, on this laptop:

1. A local copy of the **Resistor Detection** dataset (primary)  classes:
   `resistor`, `wire`, `breadboard`.
2. A YOLOv8n model trained on it, saved as `best.pt`.
3. A short markdown results summary (`training_report.md`) with: classes
   trained, image count, epoch count, final mAP@50/precision/recall, training
   wall-clock time, and the exact path to `best.pt`.
4. (Stretch, only if time remains after step 2 finishes cleanly)  repeat with
   the secondary **Electronics Components** dataset (adds `LED`, `capacitor`,
   `diode`, `transistor`, `zener diode` classes) and note in the report
   whether it's worth merging classes for a second, richer model.

---

## 2. Prerequisites  ask the human operator for these before starting

- **Roboflow private API key.** The human needs a free account at
  https://app.roboflow.com (Settings  Roboflow API  Private API Key). If
  they don't have one yet, tell them to create it now  it takes under two
  minutes and needs no payment info. Do not proceed with dataset download
  until you have this key. Never hardcode the key in a committed file; read
  it from an environment variable (`ROBOFLOW_API_KEY`) or a local
  `.env`/`secrets.txt` that you add to `.gitignore` if a git repo exists.
- Confirm whether the laptop has an NVIDIA GPU (`nvidia-smi`)  this only
  changes expected training time, not any commands below (`ultralytics`
  auto-detects CUDA if present and falls back to CPU otherwise).

---

## 3. Datasets (already identified and verified  use these, don't search for alternatives unless both fail)

| Priority | Dataset | Roboflow workspace/project | Classes | Images | License |
|---|---|---|---|---|---|
| Primary | Resistor Detection | `circuits-project` / `resistor-detection-5azes` | resistor, wire, breadboard | 756 (1,820 in latest version) | CC BY 4.0 |
| Secondary (stretch) | Electronics components | `jovine` / `electronics-components` | Resistor, Capacitor, Diode, Transistor, LED, Zener Diode | 59 | CC BY 4.0 |

Roboflow project pages (for reference / manual fork if the API path fails):
- https://universe.roboflow.com/circuits-project/resistor-detection-5azes
- https://universe.roboflow.com/jovine/electronics-components

---

## 4. Step-by-step tasks

### 4.1 Environment setup

```bash
python3 -m venv yolo-env
source yolo-env/bin/activate      # Windows: yolo-env\Scripts\activate
pip install --upgrade pip
pip install roboflow ultralytics
```

Verify install:
```bash
python3 -c "import ultralytics, roboflow; print(ultralytics.__version__)"
```

### 4.2 Download the primary dataset

Create `download_dataset.py`:

```python
import os
from roboflow import Roboflow

api_key = os.environ["ROBOFLOW_API_KEY"]  # set this before running
rf = Roboflow(api_key=api_key)

project = rf.workspace("circuits-project").project("resistor-detection-5azes")
version = project.version(5)          # check the project page for the current latest version number
dataset = version.download("yolov8")
print("Downloaded to:", dataset.location)
```

Run:
```bash
export ROBOFLOW_API_KEY="paste_the_human's_key_here"   # ask, don't invent
python3 download_dataset.py
```

Expected result: a new folder (something like `Resistor-Detection-5/`)
containing `train/`, `valid/`, `test/` subfolders and a `data.yaml`.
If the version number `5` 404s, open the project page, check the current
latest version shown there, and use that number instead.

### 4.3 Train YOLOv8n

```bash
yolo detect train \
    data=Resistor-Detection-5/data.yaml \
    model=yolov8n.pt \
    epochs=50 \
    imgsz=640 \
    batch=16 \
    name=circuitpulse_v1
```

Notes:
- `yolov8n.pt` auto-downloads pretrained COCO weights on first run  needs
  internet access once.
- If CPU-only and this is taking too long, cut to `epochs=25`  acceptable
  for a hackathon demo model, and cheaper is better than not finishing.
- Do not increase `imgsz` above 640 or switch to a larger model (`yolov8s`,
  `yolov8m`, etc.)  nano is the right tradeoff for a Raspberry Pi 5
  inference target and for a tight time budget.

### 4.4 Validate

```bash
yolo detect val model=runs/detect/circuitpulse_v1/weights/best.pt \
    data=Resistor-Detection-5/data.yaml
```

Capture the printed `mAP50`, `precision`, and `recall` for the report.

### 4.5 (Stretch goal only  do this last, only if 4.14.4 finished with time to spare)

Repeat 4.24.4 for the `jovine/electronics-components` project (adjust the
`workspace`/`project` names and re-check its version number on the project
page), training a **separate** model (`name=circuitpulse_v2_components`)
rather than merging datasets  merging label spaces from two differently
annotated Roboflow projects is not worth the risk of corrupting `data.yaml`
under time pressure. Note the second model's location and metrics in the
report too, and give a one-line recommendation on whether the human should
use it alongside or instead of the primary model.

### 4.6 Write the report

Create `training_report.md` in the project root with:

```markdown
# CircuitPulse Training Report

## Model 1  Resistor Detection (primary)
- Dataset: circuits-project/resistor-detection-5azes (version N)
- Classes: resistor, wire, breadboard
- Images: <count from data.yaml / download log>
- Epochs: <N>
- Training time: <wall-clock>
- mAP50: <value>
- Precision: <value>
- Recall: <value>
- Weights path: runs/detect/circuitpulse_v1/weights/best.pt

## Model 2  Electronics Components (stretch, if attempted)
- ... same fields, or "Not attempted  ran out of time budget" ...

## Handoff note for the Raspberry Pi
Copy the weights file to the Pi with:
  scp runs/detect/circuitpulse_v1/weights/best.pt <user>@<pi-ip>:~/circuitpulse/
On the Pi, load it with:
  from ultralytics import YOLO
  model = YOLO("best.pt")
Recommend keeping the existing HSV/ArUco classical-CV LED detector running
alongside this model, since neither trained dataset includes an LED class
with polarity labels.
```

---

## 5. Definition of done

- [ ] `Resistor-Detection-*/` folder exists locally with `data.yaml`
- [ ] `runs/detect/circuitpulse_v1/weights/best.pt` exists
- [ ] `yolo detect val` ran successfully and printed metrics
- [ ] `training_report.md` written with real (not placeholder) numbers
- [ ] Human operator told exactly which file to `scp` to the Pi and the
      exact command to do it

## 6. Guardrails

- Don't commit the Roboflow API key anywhere.
- Don't upgrade/replace `ultralytics` or `roboflow` package versions beyond
  what `pip install` resolves by default  version-pinning debugging isn't a
  good use of the remaining hackathon time.
- Don't attempt to also handle the Raspberry Pi side (vision pipeline, rule
  engine, dashboard)  that's out of scope for this file and already covered
  in `CircuitPulse_Execution_Guide.pdf`.
- If the Resistor Detection dataset download fails twice for any reason,
  stop and report back to the human rather than substituting a different,
  unverified dataset.
