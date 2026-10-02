# CircuitPulse

CircuitPulse is a local, safety-first live circuit-debugging prototype for
fixed-camera Arduino/ESP32 breadboard demonstrations. It separates *visual
evidence* from *electrical verification*: a camera may suggest a wire, but it
cannot silently prove electrical continuity.

## What is implemented

- A versioned catalog of six professor-demo blueprints: LED blink, voltage
  divider, button pull-down, PWM RGB LED, I2C sensor, and low-current motor
  driver.
- A reviewed fiducial-backed manifest platform for 14 board/module families.
  Unrecognised modules remain unsupported; identity-only markers cannot be
  used as terminal geometry until a measured layout is reviewed.
- An authoritative, revisioned graph actor with 5-of-7 temporal fusion,
  explicit ambiguity, wire-removal debounce, next-action guidance, and
  `PASS`/`FAULT`/`INCOMPLETE`/`INDETERMINATE`/`REACQUIRING` states.
- ArUco calibration, calibrated terminal mapping, conservative segmented-wire
  mask extraction, and a bridge to graph evidence. Crossings and uncertain
  endpoints are withheld for confirmation.
- Deterministic netlist checks, optional ngspice operating-point execution,
  firmware/preset contradiction checks, safe KiCad/SPICE import, module
  voltage/current/flyback envelopes, optional instrument-evidence contracts,
  and replayable safety fixtures.
- Typed circuit logic for voltage dividers, I2C pull-ups/line separation, SPI
  signal separation, GPIO current limits, inductive-load flyback protection,
  resistor dissipation, and component voltage ratings. Its ranked root causes
  feed the next physical repair action.
- An offline linear DC operating-point solver for supported resistor/source
  networks, plus a conservative combinational digital-gate evaluator. Dynamic,
  non-linear, and sequential circuits remain explicitly `INDETERMINATE` until
  a reviewed ngspice or temporal model is supplied.
- RC timing checks, measured PWM/analog/I2C-ACK checks, logic-level interface
  validation, regulator headroom checks, and MOSFET/BJT driver constraints.
- Derated power-source current budgets and op-amp common-mode/output-swing
  envelope checks for declared mixed-signal operating points.
- Worst-case divider/RC tolerance analysis, ADC-reference/raw-code validation,
  clock frequency/duty/jitter checks, power/reset/enable sequencing, and
  steady-state thermal derating.
- Waveform-level I²C/SPI/UART decoding, trace-driven temporal assertions,
  exhaustive combinational truth tables, and reviewed clocked finite-state
  machine transition tables for complex digital behavior.
- A guarded local ngspice operating-point rule for reviewed complex analog
  templates. It permits bounded `.op` analysis only, forbids ngspice shell and
  control directives, and requires every declared critical node voltage to be
  reported and inside its approved range.
- REST plus optional WebSocket live-session state streaming, with a dashboard
  fallback to polling when WebSockets are unavailable.

## Safety contract

`PASS` is possible only for a selected reviewed blueprint whose observed graph
is complete, fault-free, and user-confirmed or supported by stable,
high-confidence calibrated evidence **and** whose current graph revision has a
passing deterministic netlist/simulation report. Camera loss changes active sessions to
`REACQUIRING`; prior passes are not retained. Unknown modules, incomplete
evidence, uncertain endpoints, and unavailable simulation return a non-pass
state.

The current repository does **not** claim a trained terminal/wire model,
physical calibration, or measured electrical evidence. Those require the
actual camera, mat, boards, wiring, and instruments. The software is built to
accept them safely once produced and benchmarked.

## Run locally

```powershell
python -m pip install -r requirements.txt
python main.py --camera 0
```

For Android IP Webcam on the same Wi-Fi network, the app accepts either the
full MJPEG URL or a bare host and port. For the supplied camera address:

```powershell
python main.py --camera 192.0.0.4:8080
```

CircuitPulse normalizes that to `http://192.0.0.4:8080/video`.

The server binds to `127.0.0.1` by default and has no cloud runtime
dependency. For an intentional local-network presentation, pass
`--host 0.0.0.0` only on a trusted network.

Open `http://localhost:5000`, choose a reviewed blueprint, and begin a live
session. Generate the required printed mat/module markers before physical use:

```powershell
python tools/generate_fiducials.py --output artifacts/fiducials
```

After calibrating the real rig, create a reviewable terminal-layout candidate
from ordered physical pin clicks. It remains untrusted until reviewed and added
to the versioned module manifest:

```powershell
python tools/measure_terminal_layout.py --module-id arduino_uno --calibration artifacts/calibration.json --points artifacts/uno_terminal_pixels.json
```

Then a named reviewer must compare the candidate with the physical module.
The review tool emits a provenance-bound layout for normal version-control
review; it deliberately does not alter the live catalog by itself:

```powershell
python tools/review_terminal_layout.py artifacts/layouts/arduino_uno.candidate.json --reviewer lab-hardware-reviewer --output artifacts/layouts/arduino_uno.reviewed.json
```

The laptop runtime prefers a checksum- and benchmark-gated TensorRT engine.
Create its release manifest only after measuring the target laptop:

```powershell
python tools/write_engine_manifest.py --help
```

Complex circuit logic is supplied to `POST /api/circuit/analyze` as typed
components plus reviewed `requirements`. Every requirement is deterministic:
unsupported or missing measured evidence yields a non-pass result. The current
rule set covers linear DC, guarded SPICE `.op`/`.tran`/`.ac` measurement gates,
analog tolerance/ADC/thermal checks, digital truth/state/timing checks,
firmware contracts, protocol traces, and instrumented power sequencing.

Before a training run, place real frame and annotation artifacts beside a
dataset manifest, record their SHA-256 values, and validate that physical
assembly sessions do not leak across the train/validation/test boundary:

```powershell
python tools/validate_dataset_manifest.py path\\to\\dataset_manifest.json --require-preset led_blink
```

`benchmarks/dataset_manifest.example.json` is documentation only. It contains
placeholders and is deliberately rejected until replaced with real, checksummed
capture evidence.

For trace-driven sequential logic, import a logic-analyzer CSV with an explicit
capture-column-to-reviewed-net mapping. The import does not guess channel
identity or reorder samples:

```powershell
python tools/import_logic_trace.py capture.csv --signal CLK=clock_net --signal D=data_net --output trace.json
```

For rails, reset, enable, or regulator checks, import a timestamped
oscilloscope/meter CSV with the same explicit mapping discipline:

```powershell
python tools/import_voltage_trace.py power.csv --channel CH1=VCC --channel CH2=RESET --output power-trace.json
```

## Key API

- `GET /api/presets` and `GET /api/modules`
- `POST /api/sessions` with `{"preset_id":"led_blink"}`
- `POST /api/sessions/{id}/observations` for complete calibrated visual frames
- `POST /api/sessions/{id}/vision-graph` for canonical terminal/wire evidence
- `POST /api/sessions/{id}/confirmations` for explicit endpoint confirmation
- `POST /api/sessions/{id}/netlist/verify` binds a netlist result to the
  supplied current `graph_revision`, `graph_fingerprint`, and complete
  `terminal_nets` declaration; it is invalidated by topology changes
- `POST /api/sessions/{id}/instruments/evidence` promotes an explicit positive
  continuity measurement (`connected: true`) into graph evidence
- `GET /api/sessions/{id}/audit/verify` validates the local append-only
  evidence hash chain
- `POST /api/calibration` with a calibration-mat image
- `POST /api/netlist/verify`, `/api/firmware/analyze`, `/api/eda/import`,
  `/api/components/verify`, `/api/instruments/evidence`, and
  `/api/benchmarks/replay`
- `POST /api/simulation/operating-point` accepts a reviewed `.op` template,
  optional `expected_node_ranges_v`, and an optional bounded timeout; it never
  permits ngspice control or shell directives
- `POST /api/circuit/analyze` for typed component, protocol, and operating-limit
  analysis using `requirements` rule-pack entries
- `POST /api/presets/{preset_id}/repair-plan` and
  `GET /api/sessions/{id}/repair-plan` for ordered safe repair actions
- `GET /api/health` for camera, model, calibration, graph-session, and
  transport health.

`POST /api/benchmarks/replay` reports `development_ready` separately from
`release_ready`. The latter remains false until all six presets have a passing
fixture plus ten fault fixtures each and measured latency, accuracy, clean-boot,
and 30-minute rehearsal gates are recorded. Release coverage counts only
fixtures labelled `held_out_physical` with a capture-session ID, operator, and
a local capture artifact whose SHA-256 is verified during replay;
development/synthetic JSON fixtures can never certify release. In addition,
each preset needs at least eight distinct physical `fault_class` values among
its ten held-out fault fixtures, preventing repeated copies of one fault from
being counted as broad coverage.

## Verify

```powershell
python -m unittest -v test_netlist.py test_session.py test_intelligence.py
```

The suite is offline by default. To intentionally run the optional Raspberry
Pi detector integration test, set both a trusted deployment URL and a real
image path before test discovery:

```powershell
$env:CIRCUITPULSE_PI_URL = "http://PI_ADDRESS:5000"
$env:CIRCUITPULSE_PI_IMAGE = "C:\path\to\fixture.jpg"
python -m unittest test_pi.py
```

See [PROGRESS.md](PROGRESS.md) for completed work and mandatory physical
release gates.
