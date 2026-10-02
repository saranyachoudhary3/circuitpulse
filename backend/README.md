# CircuitPulse Backend API

The backend module handles camera streaming, real-time YOLOv8 object detection, circuit verification, and delivers the REST and MJPEG API endpoints.

## Endpoints
* GET / - Serves the interactive Web AR frontend (ar/index.html).
* GET /api/stream - High-speed MJPEG video stream (30 FPS).
* GET /api/detections - Live bounding boxes, classes, confidences, and decoded resistor values.
* GET /api/verification - Active circuit diagnosis, pin alignment errors, safety warnings, and spoken TTS guidance.
* GET /api/circuits - List of supported circuit presets.
* POST /api/trigger-autofocus - Sends autofocus pulse to connected phone camera.
* POST /api/netlist/verify - Runs deterministic electrical checks on an explicit,
  user-confirmed or schematic-imported netlist. This endpoint deliberately does
  not infer continuity from a camera frame.

## Running the Backend
python app.py
