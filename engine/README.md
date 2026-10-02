# CircuitPulse Circuit Reasoning Engine 

The engine analyzes electronic component topologies, verifies wiring continuity, and catches circuit faults in real time.

## Key Capabilities
* **Dynamic Pin Verification**: Verifies wire terminations against target schematics (e.g. catches Pin 8 plugged into Arduino when Pin 17 is required).
* **Breadboard Row Alignment**: Verifies component and wire pinholes on breadboards (Row 1-30).
* **Critical Short-Circuit Detection**: Flags direct bridges between 5V power and GND.
* **Component Protection**: Verifies current-limiting series resistors for LEDs (e.g. 220 ohms).
* **Temporal State Latching**: 15-second memory preserves verified circuit context during close-up macro inspection of individual components.
* **Microcontroller Detection**: Reports microcontroller model (e.g. ATmega328P on Arduino Uno, ESP32).

## Schematics (circuits/)
* rduino_led.json: Arduino LED blink and digital output schema.
* oltage_divider.json: Two-resistor voltage divider schema.
* reeform_safety.json: General safety and short-circuit schema.
