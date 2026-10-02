# CircuitPulse Vision Layer 

The vision module provides high-speed computer vision pipelines for embedded edge devices:

## Modules
* **resistor.py**: Analyzes 4-band resistor color codes (Red, Brown, Orange, Gold, etc.) across HSV color spaces, calculates exact resistance (e.g. 220 ohms), and formats tolerance.
* **tracker.py**: Exponential Moving Average (EMA) bounding box smoother that prevents visual jitter and tracks components across video frames.
* **DuPont Connector Filtering**: Rejects dark/black DuPont jumper cable headers based on low HSV color saturation (< 22) so they are never misidentified as resistors.
* **Collinear Wire Merging**: Merges split or fragmented ends of curved jumper wires into a single continuous wire entity.
