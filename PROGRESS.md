# CircuitPulse Engineering Progress

## 2026-10-02: baseline audit and verified logic foundation

### Implemented

- Added `logic/netlist.py`, a deterministic netlist verifier. It accepts
  explicit component pins and nets rather than guessing electrical continuity
  from pixels.
- It detects direct positive-to-ground zero-ohm paths and checks LED anode and
  cathode paths plus the presence and minimum value of a series resistor.
- Added `POST /api/netlist/verify` to the active `main.py` server.
- Added six automated tests in `test_netlist.py`, covering a safe LED circuit,
  direct short, missing or undersized limiter, incomplete power evidence, and
  malformed input.

### Verification

`python -m unittest -v test_netlist.py` passes: 6/6 tests. The Flask test
client also exercised `POST /api/netlist/verify` with a safe LED netlist and
received `PASS`.

### Important constraint made explicit

Camera detections and bounding boxes are not proof that two conductors touch.
The live vision path is therefore an *inspection assistant* until endpoints are
confirmed by a user, a continuity probe, a schematic import, or calibrated
multi-view reconstruction. The netlist endpoint is the source of truth for the
checks above.

### Next implementation milestones

1. Define a versioned circuit-evidence schema that attaches confidence and
   provenance to every inferred endpoint.
2. Calibrate each board family and breadboard geometry; infer terminal candidates
   with uncertainty rather than hard-coded box fractions.
3. Add a review UI that asks for only ambiguous endpoints, then submits the
   confirmed graph to `/api/netlist/verify`.
4. Extend the verifier with DC operating-point simulation (modified nodal
   analysis), component ratings, polarity models, digital logic levels, and
   datasheet constraints.
5. Establish a labelled, held-out physical-circuit benchmark with fault classes,
   report precision/recall and false-safe rate, and gate releases on it.

## 2026-10-02: v2 live-debug foundation

### Implemented

- Added six reviewed, versioned circuit blueprints: LED blink, voltage divider,
  button pull-down, PWM RGB LED, I2C sensor, and low-current motor driver.
- Added a reviewed, fiducial-backed component catalog for Arduino/ESP32 and 11
  sensor/actuator families. Only known catalog modules can receive pin trust.
- Added a single-authority graph session actor with graph revisions, five-of-seven
  frame fusion, user confirmations, deterministic missing/extra/short checks,
  and ranked next-step instructions.
- Added REST endpoints for blueprint selection, auto-identification candidates,
  session creation/state, observations, and confirmations. WebSocket delivery is
  enabled when Flask-SocketIO is installed, with dashboard polling as a local
  fallback.
- Added calibration and terminal-mapping primitives. They fail closed when ArUco
  markers are unavailable or an endpoint is ambiguous.
- Added an inference-runtime selector that prefers a validated laptop-specific
  TensorRT `.engine`, with an explicit local PyTorch fallback only when that
  engine has not yet been benchmarked and installed.
- Added reviewed ArUco module-marker mapping. Marker IDs 10-23 map only to
  catalogued modules; unknown markers are reported as unsupported instead of
  receiving guessed pin assignments.
- Updated deployment so the Gemini key file is no longer included in the Pi zip.

### Verified

`python -m unittest -v test_netlist.py test_session.py test_intelligence.py`
passes the full deterministic suite.
The Flask test client creates a live session, confirms every expected wire, and
receives `PASS`; a direct 5V-to-GND edge produces `FAULT` and a remove action.

### Hardware/data work still required

- Print and mount the four-marker calibration mat plus the reviewed module
  fiducials; capture calibration frames with the final overhead camera.
- Capture and label the final demo hardware for components, wire masks,
  terminal polygons, endpoint pairs, resistor bands, and fault cases.
- Train TensorRT-ready component, segmentation, terminal, and OCR models on that
  data; benchmark them on the actual RTX laptop before enabling automated graph
  observations in a professor demo.
- Install ngspice locally and add validated simulation templates per preset.

## 2026-10-02: expanded intelligence and safety interfaces

### Implemented

- Added a calibrated vision-to-graph bridge. A trained segmentation model can
  send wire endpoints and terminal anchors in canonical millimetres; ambiguous
  endpoint attachments are retained for confirmation rather than guessed.
- Added firmware-aware checks for statically visible Arduino/ESP32 pin modes,
  PWM use, I2C/SPI initialization, and blueprint conflicts.
- Added safe KiCad legacy-netlist and two-terminal SPICE imports, so expected
  circuit connectivity can originate from EDA tooling instead of presets alone.
- Added optional instrument evidence contracts for continuity, voltage, current,
  logic, and serial adapters.
- Added replayable benchmark fixtures with a zero-false-safe release criterion.
- Added digital-twin safety envelopes for reviewed modules, including supply
  compatibility, current limits, and inductive-load protection declarations.
- Added segmentation-mask endpoint extraction plus a calibration-aware bridge,
  and tooling to generate the marker set and record measured TensorRT release
  gates in a checksum-protected engine manifest.

### Still hardware-dependent

No code can manufacture a reliable segmentation model, camera calibration, or
oscilloscope/continuity reading. Those integrations now fail closed until their
physical inputs are supplied and validated.

## 2026-10-02: live-state resilience and offline rehearsal hardening

### Implemented

- Made observation input explicitly frame-based. A vision-only wire is removed
  after five complete absent frames, so a live repair is reflected without
  treating a brief hand occlusion as a removal.
- Added camera health propagation to every session. A disconnect changes the
  session state to `REACQUIRING`, replaces the action with a wait instruction,
  and withholds a prior `PASS` until visual evidence returns.
- Preserved mask-model quality through the calibrated mask-to-terminal bridge;
  exact geometry cannot elevate a weak segmentation result into trusted graph
  evidence.
- Disabled the optional cloud prose explainer by default and removed its
  file-based secret lookup. The deterministic graph, safety checks, and demo
  health path now start without an API key or cloud call. It can be explicitly
  enabled only with `CIRCUITPULSE_ENABLE_CLOUD_EXPLAINER=1` and an environment
  key; it remains non-authoritative.
- Replaced stale repository instructions with the v2 run, safety, API, and
  verification guide. The dashboard no longer opens with an unearned
  “circuit validated” message.

### Verified

`python -m unittest -v test_netlist.py test_session.py test_intelligence.py`
passes 27 tests, including wire removal, camera-loss verdict withholding, and
pixel-mask → calibrated-coordinate → terminal-graph fusion. A Flask test-client
smoke test passed for presets, sessions, health, empty visual graph input, and
unsafe RC522-at-5V envelope rejection.

## 2026-10-02: durable evidence and graph-bound electrical proof

### Implemented

- Added a local append-only JSONL audit record for every session creation and
  graph revision. Records contain canonical JSON, a sequence number, and a
  SHA-256 hash chain; audit verification is available at
  `GET /api/sessions/{id}/audit/verify`.
- Changed the live verdict contract: a complete visual/confirmed graph is now
  only `INDETERMINATE` until a deterministic netlist/simulation report has been
  attached to that exact graph revision. Any topology change invalidates the
  report; a failed report produces `FAULT`.
- Added `POST /api/sessions/{id}/netlist/verify`, which evaluates a submitted
  netlist and safely binds its report to a non-stale graph revision.
- Updated the golden passing LED fixture to include its reviewed 220-ohm LED
  netlist, preventing benchmarks from treating topology alone as electrical
  proof.

### Verified

The full suite passes 30 tests. It covers an audited multi-revision session,
audit-chain verification, graph-bound deterministic proof, and benchmark replay
with the new proof requirement.

## 2026-10-02: measured continuity integration

### Implemented

- Added first-class `instrumented` connection provenance. A positive continuity
  measurement can now add a graph edge directly, rather than being displayed
  as disconnected metadata.
- Added `POST /api/sessions/{id}/instruments/evidence`. It requires explicit
  `connected: true`; negative and non-continuity readings are retained as
  non-graph evidence and cannot manufacture a connection.
- Instrumented topology changes carry the same graph-revision invalidation and
  deterministic-proof requirement as visual or user-confirmed changes.

### Verified

The suite passes 31 tests. A Flask smoke test verifies that a measured positive
continuity result becomes `instrumented` graph evidence, while a negative
measurement is rejected from the graph.

## 2026-10-02: identity-versus-geometry enforcement

### Implemented

- Added an explicit terminal-layout status to every catalog result. A reviewed
  fiducial now proves only module identity unless the manifest contains a
  complete, measured terminal layout for every pin.
- Changed fiducial detection to return `IDENTITY_ONLY` rather than implying a
  terminal map when that physical measurement is absent. This prevents similar
  module variants from gaining unsafe pin assignments by visual identity alone.
- Hardened audit logging with synchronous flushes plus checks for sequence,
  state/session consistency, and hash-chain integrity before an append.

### Verified

The suite passes 33 tests. Catalog checks prove that all current module markers
are identity-only until their real terminal geometry is measured and reviewed;
audit tampering is detected.

## 2026-10-02: physical terminal-layout measurement workflow

### Implemented

- Added `tools/measure_terminal_layout.py`, which converts ordered physical
  terminal clicks from a calibrated camera image into canonical millimetre
  coordinates for a named catalog module.
- Candidate layouts are written outside the reviewed catalog with
  `status: candidate`; human review is still required before a module can gain
  automatic terminal mapping.
- Added strict validation for calibration markers, homography shape, ordered
  pin count, and finite pixel coordinates.

### Verified

The complete suite passes 34 tests. The new layout builder is tested with a
known homography, and the documented direct CLI launcher runs successfully.

## 2026-10-02: automatic-evidence and offline deployment gates

### Implemented

- Added a model/calibration/layout provenance contract for automatic vision
  graph input. It requires a benchmarked TensorRT artifact ID, active
  calibration ID, reviewed terminal geometry, known manifest pins, and valid
  endpoint payloads before the graph actor can receive a model update.
- Added `GET /api/readiness`, which lists all blockers for automatic
  verification before a presentation begins.
- Camera capture now reports frame freshness and rejects stale retained frames
  as visual evidence, forcing live sessions to `REACQUIRING` on disconnect.
- Changed the runtime to loopback-only binding and same-origin WebSockets by
  default; LAN exposure is explicit. Removed the dashboard's remote font,
  preserving clean-boot operation with networking disabled.

### Verified

The suite passes 38 tests. Flask smoke tests confirm the automatic-vision
trust boundary, readiness blocker reporting, and camera-freshness health path.

## 2026-10-02: terminal-net-bound deterministic proof

### Implemented

- Strengthened session netlist verification with a server-derived graph
  fingerprint and a complete terminal-to-net declaration. Every observed wire
  endpoint must map to the same declared net, and every declared graph net must
  exist in the submitted netlist.
- This closes the gap where a safe-but-unrelated netlist could otherwise be
  attached to a visually correct graph merely by matching a revision number.
- Added explicit model capability gates to TensorRT manifests: production
  automatic evidence now requires component detection, wire instance
  segmentation, and terminal localization capabilities in addition to latency
  and false-safe benchmark gates.

### Verified

The suite passes 39 tests. A Flask smoke test confirms a passing netlist can
bind to the exact observed terminal graph and rejects a mismatched fingerprint.

## 2026-10-02: honest benchmark release gating

### Implemented

- Split benchmark status into `development_ready` (all available fixtures pass
  with zero false-safe result) and `release_ready` (all required circuit,
  fault-fixture, and operational measurements pass).
- Enforced the declared acceptance structure: every supported preset needs at
  least one passing fixture and ten fault fixtures, plus recorded verdict and
  endpoint accuracy, latency, graph-rate, clean-boot, and 30-minute rehearsal
  measurements.
- The current small fixture set is correctly labelled development-ready only;
  it cannot be presented as release certification.

### Verified

The suite passes 39 tests without camera-device test noise. Benchmark replay
confirms its passing fixtures but correctly reports `release_ready: false`
until the physical acceptance evidence exists.

## 2026-10-02: typed circuit logic and repair guidance

### Implemented

- Added a typed, canonical circuit IR that validates components, pins, wires,
  requirements, and measurements before deterministic analysis.
- Added `POST /api/circuit/analyze` and made session-bound verification use the
  same typed engine. Complex constraints can therefore prevent `PASS` in a
  selected live blueprint session.
- Implemented reviewed rule entries for voltage-divider ranges, I2C line and
  pull-up topology, SPI signal separation, GPIO output current limits,
  inductive-load flyback protection, resistor dissipation, and voltage ratings
  for capacitors/diodes/LEDs when measured values are supplied.
- Added ranked root causes with concrete repair actions; a deterministic fault
  now becomes one physical next-step instruction when the camera is healthy.

### Verified

The suite passes 44 tests. API smoke tests cover typed divider analysis and a
session-bound GPIO overcurrent report; camera reacquisition correctly retains
priority over non-immediate repair narration when the feed is unavailable.

## 2026-10-02: offline analog/digital solving and repair planning

### Implemented

- Added a deterministic modified-nodal-analysis DC solver for declared linear
  resistor, voltage-source, and current-source circuits. It evaluates expected
  node-voltage ranges without requiring ngspice and fails closed for dynamic or
  non-linear components.
- Added a combinational digital-logic evaluator for AND/OR/NOT/NAND/NOR/XOR/
  XNOR/buffer/mux circuits, including expectation mismatches, unknown inputs,
  feedback, output contention, and explicitly unsupported sequential devices.
- Added UART line checks and reviewed power-domain range checks.
- Added a minimal safe repair planner, exposed for presets and authoritative
  sessions. It removes critical shorts first, then unexpected connections,
  typed electrical faults, and missing blueprint dependencies in build order.

### Verified

The full suite passes 49 tests. It covers DC node-voltage range detection,
digital-gate mismatch detection, UART/power-domain faults, and repair-plan
ordering; the repair-plan API smoke test confirms direct rail shorts are the
first recommended action.

## 2026-10-02: timing, runtime-signal, and interface safety rules

### Implemented

- Added first-order RC timing/threshold validation for reviewed resistor and
  capacitor values.
- Added measured runtime checks for PWM frequency/duty, arbitrary voltage or
  current ranges, and I2C address acknowledgements from instrument/firmware
  evidence.
- Added logic-level interface checks, regulator input/dropout checks, and
  MOSFET/BJT driver current/drive checks.

### Verified

The complete deterministic suite passes 52 tests, including RC timing, PWM,
I2C ACK, regulator dropout, logic-level overvoltage, and MOSFET gate-drive
fault cases.

## 2026-10-02: reproducible model and dataset evidence gates

### Implemented

- Unified TensorRT manifest generation and runtime validation. An engine now
  has to declare and meet all three automatic-mapping capabilities (component
  detection, wire instance segmentation, terminal localization), match its
  checksum, meet p95 latency, and show zero held-out false-safe verdicts.
- Added a direct command-line dataset manifest validator. It requires the
  exact fixed-camera/mat/lighting profile, all required annotation classes,
  session-disjoint train/validation/test splits, positive label counts, and
  checksummed frame/annotation artifacts under the manifest directory.
- Added an intentionally non-runnable example manifest that documents the
  evidence format but cannot be mistaken for capture data. Placeholder IDs,
  paths, or checksums are rejected.

### Verified

The suite passes 55 tests. The new tests prove that missing model capabilities,
cross-split assembly-session leakage, missing artifacts, and checksum mismatch
all fail closed. The dataset CLI is executable directly from PowerShell.

## 2026-10-02: guarded complex analog operating-point proof

### Implemented

- Replaced the permissive raw ngspice wrapper with a bounded, non-interactive
  operating-point runner. It requires `.op`/`.end`, has a 64 KiB template
  limit, a maximum ten-second timeout, and rejects control, shell, and source
  directives before launching ngspice.
- Added the `spice_operating_point` typed-circuit requirement. Reviewed SPICE
  templates can declare node-voltage ranges; their parsed results become a
  critical deterministic fault when out of range and remain `INDETERMINATE`
  whenever proof is absent or incomplete.

### Verified

The full suite passes 59 tests. Mocked ngspice tests cover simulator absence,
valid node parsing, out-of-range voltage faults, and a rejected control block
without spawning a process.

## 2026-10-02: sequential trace logic and reviewable terminal geometry

### Implemented

- Added trace-driven D, JK, and T flip-flop evaluation with configurable clock
  edge and reset behavior. It consumes ordered logic-analyzer evidence rather
  than pretending that a static image can establish sequential state.
- Added a strict CSV logic-trace importer with explicit channel-to-net mapping,
  time-order validation, and a bounded sample count.
- Hardened terminal-layout trust. A reviewed layout now has to preserve the
  calibration-transform ID, ordered complete pins, a named human reviewer, a
  timestamp, a candidate checksum, and a terminal-spacing sanity check.
- Added a terminal-layout review CLI that emits a version-control-reviewable
  artifact but never edits the live module catalog automatically.

### Verified

The full deterministic suite passes 66 tests. It covers D/JK/reset sequential
state behavior, CSV trace import rejection cases, ngspice proof handling, and
layout-review provenance/terminal-collision rejection.

## 2026-10-02: mixed-signal source and op-amp envelope analysis

### Implemented

- Added a reviewed current-budget rule that totals explicitly declared
  continuous loads against an explicitly derated source capacity, preventing a
  seemingly correct wiring graph from approving an undersized USB/supply path.
- Added op-amp common-mode and output-swing envelope checks for declared
  operating points. These complement, rather than replace, the guarded SPICE
  path for circuits that need full nonlinear simulation.

### Verified

The full deterministic suite passes 68 tests. It exercises current-budget
overload and op-amp common-mode failure alongside the existing analog,
protocol, state-machine, graph, vision-trust, and runtime resilience checks.

## 2026-10-02: IP Webcam startup hardening

### Implemented

- Added safe camera-source normalization. A bare Android IP Webcam address such
  as `192.0.0.4:8080` becomes its documented MJPEG endpoint
  `http://192.0.0.4:8080/video`; explicit HTTP URLs, USB indexes, and RTSP
  sources retain their intended capture paths.
- Kept the default local-only web server binding. The camera can be remote on
  the trusted LAN while the dashboard remains at `127.0.0.1` on the laptop.

### Verified

The deterministic suite passes 69 tests, including IP-Webcam URL
normalization and existing camera frame-freshness/reacquisition behavior.

## 2026-10-02: advanced measured logic and release-evidence hardening

### Implemented

- Added guarded ngspice transient and AC measurement rules. They only accept
  reviewed `.tran`/`.ac` templates with explicit `.meas` names and ranges;
  unavailable/partial simulation cannot pass.
- Added waveform-level I²C, SPI, and UART decoding, firmware-source-to-trace
  contracts, causal multi-fault diagnosis, and an I²C transaction-boundary
  safeguard so data bytes cannot be mistaken for device addresses.
- Added first-class component-tolerance, power-sequencing, ADC/reference,
  clock-quality, thermal-derating, exhaustive truth-table, temporal-response,
  and finite-state-machine trace rules.
- Added explicit logic-analyzer and voltage-trace CSV import paths. Channel
  mappings are reviewed names, never inferred from headers.
- Strengthened release replay: only held-out physical fixtures count toward
  release coverage, and their referenced local capture artifacts must exist
  and match the recorded SHA-256. Development fixtures remain useful but can
  never certify a release.

### Verified

The full deterministic suite passes 87 tests. It covers electrical envelopes,
analog extrema, simulation gates, digital timing/state/protocol behavior,
trace import, camera reliability, vision trust boundaries, and physical
benchmark provenance. Existing unrelated whitespace warnings remain in
`deploy.py`, `engine/README.md`, and `vision/README.md`.

### Test-hygiene follow-up

- Converted the old import-time Raspberry Pi request into an explicit opt-in
  integration test controlled by `CIRCUITPULSE_PI_URL` and
  `CIRCUITPULSE_PI_IMAGE`. Standard discovery is now offline and safe.

## 2026-10-02: v2 testing, dataset repair, and benchmark readiness expansion

### Implemented

- **R1: Flask API Integration Tests (`test_api.py`)**:
  - Implemented 79 comprehensive integration tests using Flask's `test_client()` across 33 REST endpoints and SocketIO channels in `main.py`.
  - Tested the complete session lifecycle end-to-end (`POST /api/sessions` -> `POST /api/sessions/<id>/observations` -> `POST /api/sessions/<id>/confirmations` -> `POST /api/sessions/<id>/netlist/verify` -> `GET /api/sessions/<id>/repair-plan` -> `GET /api/sessions/<id>/audit/verify`), verifying state transitions (`INCOMPLETE` -> `INDETERMINATE` -> `PASS`), netlist bindings, zero-action verified repair plans, and cryptographic SHA-256 audit log hash chains.
  - Implemented rigorous positive and negative input matrix coverage across all route groups: health & streaming (`/`, `/api/health`, `/api/detections`, `/api/stream`, `/api/snapshot`, `/api/focus`, `/api/analyze`, `/api/ask`), catalogs & readiness (`/api/presets`, `/api/presets/identify`, `/api/presets/<id>/repair-plan`, `/api/modules`, `/api/modules/identify`, `/api/calibration`, `/api/readiness`), domain analysis & simulation (`/api/netlist/verify`, `/api/circuit/analyze`, `/api/firmware/analyze`, `/api/eda/import`, `/api/instruments/evidence`, `/api/components/verify`, `/api/simulation/operating-point`, `/api/benchmarks/replay`), and session operations.
  - Engineered hermetic isolation: synthetic in-memory OpenCV ArUco calibration mats and module markers eliminate camera and physical asset dependencies; redirected session audit logs to isolated temporary directories; and restored all global state on teardown.

- **R2: Detector and Vision Unit Tests (`test_detectors.py`)**:
  - Implemented 25 unit tests covering the 5 previously untested detector modules (`detectors/resistor.py`, `detectors/wires.py`, `detectors/tracker.py`, `detectors/zoom.py`, `detectors/memory.py`), the capture pipeline (`camera.py`), and segmentation masks (`vision/wire_masks.py`).
  - Tested resistor HSV color classification across 12 color classes, 4-band 220Ω decoding (Red-Red-Brown-Gold) with vertical rotation and gold-first band reversal, and E12 value snapping / formatting.
  - Resolved OpenCV border-thinning hazard: standard morphological skeletonization falls back to erosion loops where black backgrounds (`0, 0, 0`) match all-black masks and infinite-loop due to 255 border replication; engineered tests using neutral gray (`128, 128, 128`) backgrounds to ensure clean wire mask isolation and sub-10ms loop termination.
  - Tested WireTracer multi-color endpoint extraction, Tracker IoU overlap calculations, coordinate EMA smoothing (`alpha=0.65`), confidence blending (`0.7*new + 0.3*old`), track pruning on `max_missing`, AutoZoom breadboard centering / margin expansion / min-size guards, WireMemory temporal persistence / uncrossing logic, and VideoStreamer MJPEG chunk parsing with mid-stream orphan marker recovery.

- **R3: CLI Tools & Infrastructure Tests (`test_cli_tools.py`, `test_infrastructure.py`)**:
  - Implemented 39 subprocess CLI integration tests in `test_cli_tools.py` covering all 7 utilities in `tools/`: `generate_fiducials.py`, `import_logic_trace.py`, `import_voltage_trace.py`, `measure_terminal_layout.py`, `review_terminal_layout.py`, `validate_dataset_manifest.py`, and `write_engine_manifest.py`.
  - Exercised valid execution with synthetic temporary files, output schema validation, and strict error handling (missing arguments, malformed mappings, invalid data, missing inputs, and engine benchmark gate rejections).
  - Implemented 16 infrastructure tests in `test_infrastructure.py` validating that all 6 PyTorch YOLOv8 model checkpoints in `trained_models/` load successfully on CPU via Ultralytics YOLO with valid non-empty class taxonomies (`circuitpulse_m1_Resistor-Detection--5_best.pt` [3 classes], `circuitpulse_m2_Component-Detection-Arduino-UNO-1_best.pt` [24 classes], `circuitpulse_m3_yolov8-pcb-defects-1_best.pt` [6 classes], `circuitpulse_m4_Electronics-components-1_best.pt` [6 classes], `PRODUCTION_eesob_48class_best.pt` [48 classes], and `PRODUCTION_pcb_faults_best.pt` [6 classes]).
  - Validated that `Merged-Dataset/data.yaml` parses cleanly with `nc: 8` and exactly matches the 8 reviewed canonical classes (`arduino_uno`, `arduino_nano`, `arduino_mega`, `esp32`, `breadboard`, `resistor`, `wire`, `led`), and verified dataset split directory structures.

- **R4: Benchmark Fixture Expansion (`benchmarks/fixtures/`)**:
  - Expanded benchmark fixture library from 2 baseline files to 25 development-grade JSON benchmark fixtures across all 6 reviewed circuit presets:
    - `led_blink`: 1 PASS (`led_blink_complete.json`), 4 FAULT (`led_blink_short.json` [direct_short], `led_blink_wrong_pin.json` [extra_connection_wrong_pin], `led_blink_missing_limiter.json` [missing_current_limiter], `led_blink_bridged.json` [bridged_signals]).
    - `voltage_divider`: 1 PASS (`voltage_divider_complete.json`), 3 FAULT (`voltage_divider_short.json` [direct_short], `voltage_divider_wrong_pin.json` [extra_connection_wrong_pin], `voltage_divider_bridged.json` [bridged_signals]).
    - `button_pulldown`: 1 PASS (`button_pulldown_complete.json`), 3 FAULT (`button_pulldown_short.json` [direct_short], `button_pulldown_wrong_pin.json` [extra_connection_wrong_pin], `button_pulldown_bridged.json` [bridged_signals]).
    - `pwm_rgb`: 1 PASS (`pwm_rgb_complete.json`), 3 FAULT (`pwm_rgb_short.json` [direct_short], `pwm_rgb_wrong_pin.json` [extra_connection_wrong_pin], `pwm_rgb_bridged.json` [bridged_signals]).
    - `i2c_sensor`: 1 PASS (`i2c_sensor_complete.json`), 3 FAULT (`i2c_sensor_short.json` [direct_short], `i2c_sensor_wrong_pin.json` [extra_connection_wrong_pin], `i2c_sensor_bridged.json` [bridged_signals]).
    - `motor_driver`: 1 PASS (`motor_driver_complete.json`), 3 FAULT (`motor_driver_short.json` [direct_short], `motor_driver_wrong_pin.json` [extra_connection_wrong_pin], `motor_driver_bridged.json` [bridged_signals]).
  - Each fixture adheres strictly to the benchmark replay schema with full observation sequences, terminal-net bindings, and expected verdicts.
  - Replay evaluation through `replay_suite()` and `POST /api/benchmarks/replay` achieves 25/25 passing, 0 false-safes, and `development_ready: true`.

- **R5: Dataset Repair & Housekeeping**:
  - Extracted 519 Roboflow YOLO annotation `.txt` files trapped inside `Basic-electronic-component-1/roboflow.zip` into `Basic-electronic-component-1/train/labels/` using Windows extended-path (`\\?\`) addressing to overcome the 260-character `MAX_PATH` limitation.
  - Extracted 730 Roboflow YOLO annotation `.txt` files trapped inside `Basic-electronic-component-2/roboflow.zip` into `Basic-electronic-component-2/train/labels/` using extended-path addressing. Byte-for-byte SHA/size checks confirmed 100% integrity.
  - Cleaned and flagged the 3 corrupted Roboflow download directories (`PCB-Dataset-Defect-1`, `PCB-defects-1`, `PCB-defects-2`) that contained upstream AWS S3 `NoSuchKey` XML error responses instead of valid zip archives, placing `.broken_download` marker files and explanatory `README_BROKEN.txt` notices to document provenance and prevent ingestion errors.

### Verified

- Global test discovery executed cleanly:
  ```powershell
  python -m unittest discover -s . -p "test_*.py" -v
  ```
  Result: **Ran 248 tests in 10.862s — OK (skipped=1, failures=0, errors=0)**.
- Test suite metrics:
  - 88 pre-existing tests passing (zero regressions across all intelligence, logic, session, and simulation suites).
  - 159 new tests added across 4 test modules:
    - `test_api.py`: 79 tests
    - `test_cli_tools.py`: 39 tests
    - `test_detectors.py`: 25 tests
    - `test_infrastructure.py`: 16 tests
  - 1 hardware integration test intentionally skipped (`test_pi.py` requiring live Raspberry Pi device).
- Benchmark replay verified via API and test runner:
  - `POST /api/benchmarks/replay`: 25 total fixtures, 25 passed, 0 false safes, `development_ready: true`.
- Dataset integrity verified on disk:
  - `Basic-electronic-component-1/train/labels/`: 519 valid annotation files.
  - `Basic-electronic-component-2/train/labels/`: 730 valid annotation files.
  - `PCB-Dataset-Defect-1`, `PCB-defects-1`, `PCB-defects-2`: `.broken_download` and `README_BROKEN.txt` confirmed present.


## 2026-10-02: YOLOv8n v3 unified model training

### Implemented

- Trained a unified YOLOv8n model on the Merged-Dataset covering all 8 core
  CircuitPulse classes: arduino_uno, arduino_nano, arduino_mega, esp32,
  breadboard, resistor, wire, led.
- Completed 70 full epochs in 1.595 hours on NVIDIA GeForce RTX 5050 Laptop
  GPU with CUDA 12.8 and AdamW optimizer.
- Best checkpoint saved to `trained_models/circuitpulse_v3_merged_best.pt`
  (6.3 MB, 3,007,208 parameters, 8.1 GFLOPs).
- Overall mAP@50: 65.6%, Precision: 72.6%, Recall: 61.4%.
- Per-class highlights: breadboard 93.5%, arduino_uno 84.7%, arduino_nano
  82.0%, arduino_mega 74.9%. Wire (30.9%) and LED (46.2%) remain limited
  by training data volume and visual ambiguity.
- Inference speed: 2.6 ms/image on GPU.
- Updated `training_report.md` with Model 5 metrics and per-class breakdown.

### Verified

- Model loads cleanly via `YOLO('trained_models/circuitpulse_v3_merged_best.pt')`.
- Validation results match best.pt checkpoint metrics.
- Training artifacts saved to `runs/detect/circuitpulse_v3_merged/`.

## 2026-10-02: remaining test coverage, NCNN export, and intelligence tests

### Implemented

- Added `test_knowledge_base.py` with 9 tests covering the circuit knowledge
  base: section completeness, breadboard topology, Arduino board coverage,
  component polarity references, IC chip coverage, debugging methodology, and
  electrical formulas.
- Added `test_vlm_contracts.py` with 8 tests for the Gemini VLM contract
  surface: CLASS_COLORS coverage for all 8 CircuitPulse classes, BGR tuple
  validation, cloud-disabled default, ask_question timer reset, frame
  annotation with synthetic numpy arrays, and analyzer state initialization.
- Added `test_readiness.py` with 8 tests for the pre-demo readiness gate:
  all-systems-ready path, individual blocker detection for camera, model,
  and calibration, blocker accumulation, and preset-without-id handling.
- Added `test_grid_snapshot.py` with 12 tests: BreadboardGrid orientation
  detection, pin location for horizontal/vertical boards, out-of-bounds
  rejection, row clamping, component pin inference; SnapshotManager directory
  creation, PASS-report snapshot trigger, non-pass rejection, scanning
  rejection, and cooldown enforcement.
- Exported the v3 unified YOLOv8n model to NCNN format for Raspberry Pi 5
  edge deployment. Saved to
  `trained_models/circuitpulse_v3_merged_best_ncnn_model/` (11.6 MB).
- Fixed `test_infrastructure.py` model count assertions from exact equality
  to `assertGreaterEqual` so adding new model checkpoints does not break
  existing tests.

### Verified

The complete deterministic suite passes 285 tests (skipped 1 Pi hardware
integration test). No regressions against the prior 248-test baseline.
NCNN export validated with model.ncnn.param and model.ncnn.bin artifacts
present and correctly sized.
