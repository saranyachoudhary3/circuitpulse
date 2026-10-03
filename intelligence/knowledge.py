"""
CircuitPulse Circuit Knowledge Base.
Injected into the Gemini VLM prompt to enable deep circuit understanding.
"""

BREADBOARD_KNOWLEDGE = """
BREADBOARD TOPOLOGY (CRITICAL -- you MUST use this to trace connections):
- A standard breadboard has numbered ROWS (1-30 or 1-63) and lettered COLUMNS (a-e on left, f-j on right).
- Each ROW on one side (e.g., row 10, columns a-e) is internally connected. All 5 holes in that half-row are ONE electrical node.
- The CENTER GAP separates left (a-e) from right (f-j). Row 10 left is NOT connected to row 10 right.
- ICs/chips straddle the center gap: pin 1 goes in column e, pin 2 in column d, etc. on the left; pins on the other side go in f, g, etc. on the right.
- POWER RAILS (bus strips) run along the top and bottom edges, marked with + (red) and - (blue/black). All holes on one rail are connected horizontally.
- Some breadboards have a BREAK in the power rail at the midpoint. If so, you must bridge it with a jumper.

CONNECTION RULES:
- Two components are electrically connected ONLY IF they share the same half-row (same row number, same side of gap).
- To connect a component on the left side to one on the right side, use a jumper wire between the two half-rows.
- Power rail + connects to VCC/5V/3.3V. Power rail - connects to GND.
- To power the breadboard, connect Arduino 5V pin to + rail, and Arduino GND to - rail.
"""

ARDUINO_KNOWLEDGE = """
ARDUINO UNO PIN REFERENCE:
- Digital pins 0-13: General purpose I/O. Pins 0,1 = Serial (TX/RX, avoid using). Pins 3,5,6,9,10,11 = PWM (~).
- Analog pins A0-A5: Analog input (0-1023). Can also be used as digital pins 14-19.
- Pin 13: Has built-in LED on the board.
- 5V pin: Outputs 5V (max 500mA from USB).
- 3.3V pin: Outputs 3.3V (max 50mA).
- GND pins: Ground reference (there are 3 GND pins).
- VIN: Raw input voltage (7-12V).
- AREF: Analog reference voltage.
- I2C: SDA=A4, SCL=A5.
- SPI: MOSI=11, MISO=12, SCK=13, SS=10.

ARDUINO NANO: Same pin layout as Uno but smaller form factor. Plugs directly into breadboard.
ARDUINO MEGA: 54 digital pins (15 PWM), 16 analog inputs. I2C: SDA=20, SCL=21.
ESP32: 3.3V logic. GPIO pins are NOT 5V tolerant. Has WiFi/Bluetooth. ADC on most pins.
"""

COMPONENT_KNOWLEDGE = """
COMMON COMPONENTS AND HOW TO CONNECT THEM:

LED:
- Has polarity. LONGER leg = Anode (+), SHORTER leg = Cathode (-).
- Anode connects to signal/power through a current-limiting resistor.
- Cathode connects to GND.
- ALWAYS needs a resistor in series (typically 220-330 ohm for 5V, 100-150 ohm for 3.3V).
- Forward voltage: Red=2.0V, Green=2.2V, Blue=3.3V, White=3.3V.

RESISTOR:
- No polarity (can go either direction).
- Color code: Black=0, Brown=1, Red=2, Orange=3, Yellow=4, Green=5, Blue=6, Violet=7, Gray=8, White=9. Gold=5% tolerance, Silver=10%.
- Common values: 220 (Red-Red-Brown), 330 (Orange-Orange-Brown), 1K (Brown-Black-Red), 10K (Brown-Black-Orange).

CAPACITOR:
- Ceramic (small, flat): No polarity.
- Electrolytic (cylindrical, with stripe): HAS POLARITY. Stripe/shorter leg = negative. WRONG POLARITY CAN EXPLODE.
- Used for filtering (100nF ceramic near IC power pins), timing (with 555), and smoothing.

TRANSISTOR (NPN like 2N2222, BC547):
- 3 pins: Base (B), Collector (C), Emitter (E). Pinout varies by package.
- Acts as a switch: small current into Base controls large current through Collector-Emitter.
- Base needs a resistor (1K-10K) from Arduino digital pin.
- Collector connects to load (motor, relay). Emitter to GND.

TRANSISTOR (MOSFET like IRF520):
- 3 pins: Gate (G), Drain (D), Source (S).
- Gate connects to Arduino pin (through 100-220 ohm resistor). Pull-down resistor (10K) from Gate to GND.
- Drain connects to load. Source to GND.

DIODE (1N4007):
- Has polarity. Band/stripe = Cathode (-).
- Used for reverse voltage protection and flyback protection on motors/relays.
- Flyback diode: Cathode to motor+, Anode to motor- (reversed across the motor).

POTENTIOMETER:
- 3 pins: Left=one end, Center=wiper (output), Right=other end.
- Voltage divider: Left to 5V, Right to GND, Center to analog pin.
- Variable resistor: Use Center + one end only.

SERVO MOTOR:
- 3 wires: Red=5V, Brown/Black=GND, Orange/Yellow/White=Signal.
- Signal connects to a PWM pin on Arduino.
- Needs 5V power (can draw 500mA+, may need external power supply).

DC MOTOR:
- No polarity for rotation direction (swap wires to reverse).
- NEVER connect directly to Arduino pin (draws too much current).
- Use a transistor (NPN + flyback diode) or motor driver (L293D, L298N).

BUZZER:
- Passive buzzer: Needs PWM signal (use tone() function). Has polarity.
- Active buzzer: Just needs HIGH/LOW. Has polarity. + leg is longer.

ULTRASONIC SENSOR (HC-SR04):
- 4 pins: VCC=5V, GND=GND, Trig=digital output pin, Echo=digital input pin.
- Trig sends 10us pulse, Echo returns pulse proportional to distance.

PIR MOTION SENSOR:
- 3 pins: VCC=5V, GND=GND, OUT=digital input pin.
- OUT goes HIGH when motion detected.

LDR (Light Dependent Resistor):
- No polarity. Resistance decreases with light.
- Voltage divider with fixed resistor (10K): LDR to 5V, junction to analog pin, 10K to GND.

DHT11/DHT22 (Temperature/Humidity):
- 3 used pins (4-pin package): VCC=3.3-5V, Data=digital pin (with 10K pull-up to VCC), GND.

LCD 16x2 (with I2C backpack):
- 4 wires: VCC=5V, GND=GND, SDA=A4, SCL=A5.

RELAY MODULE:
- 3 control pins: VCC=5V, GND=GND, IN=digital pin (LOW activates most modules).
- Load side: COM, NO (normally open), NC (normally closed).
"""

IC_KNOWLEDGE = """
COMMON IC PINOUTS:

555 TIMER (8-pin DIP):
- Pin 1: GND
- Pin 2: Trigger (start timing when pulled LOW)
- Pin 3: Output
- Pin 4: Reset (connect to VCC if not used)
- Pin 5: Control Voltage (connect 10nF cap to GND if not used)
- Pin 6: Threshold
- Pin 7: Discharge
- Pin 8: VCC (4.5-16V)
- ASTABLE mode (oscillator): R1 between VCC and pin 7, R2 between pin 7 and pin 6, C between pin 6 and GND. Pins 2+6 connected.
- MONOSTABLE mode (one-shot): Trigger on pin 2, timing set by R*C.

L293D MOTOR DRIVER (16-pin DIP):
- Pin 1: Enable 1,2 (HIGH to enable motor A)
- Pin 2: Input 1 (motor A direction)
- Pin 3: Output 1 (motor A terminal)
- Pin 4,5: GND (also heat sink)
- Pin 6: Output 2 (motor A terminal)
- Pin 7: Input 2 (motor A direction)
- Pin 8: VCC2 (motor supply, up to 36V)
- Pin 9: Enable 3,4 (HIGH to enable motor B)
- Pin 10: Input 3 (motor B direction)
- Pin 11: Output 3 (motor B terminal)
- Pin 12,13: GND
- Pin 14: Output 4 (motor B terminal)
- Pin 15: Input 4 (motor B direction)
- Pin 16: VCC1 (logic supply, 5V)
- Straddles breadboard gap. Pin 1 top-left, pin 8 bottom-left, pin 9 bottom-right, pin 16 top-right.

LM7805 VOLTAGE REGULATOR (TO-220):
- Pin 1 (left): Input (7-35V)
- Pin 2 (center): GND
- Pin 3 (right): Output (5V regulated)
- Add 0.33uF cap on input, 0.1uF cap on output for stability.

SHIFT REGISTER 74HC595 (16-pin DIP):
- Pin 8: GND, Pin 16: VCC
- Pin 14: Serial Data In (SER/DS)
- Pin 11: Clock (SRCLK/SH_CP)
- Pin 12: Latch (RCLK/ST_CP)
- Pin 13: Output Enable (active LOW, connect to GND)
- Pin 10: Reset (active LOW, connect to VCC)
- Pins 15, 1-7: Outputs QA-QH

OP-AMP LM358 (8-pin DIP):
- Pin 1: Output A, Pin 2: Inverting Input A (-), Pin 3: Non-Inverting Input A (+)
- Pin 4: GND, Pin 8: VCC
- Pin 5: Non-Inverting Input B (+), Pin 6: Inverting Input B (-), Pin 7: Output B
"""

CIRCUIT_PATTERNS = """
COMMON CIRCUIT PATTERNS TO RECOGNIZE:

VOLTAGE DIVIDER:
- Two resistors in series between VCC and GND.
- Output taken from the junction = VCC * R2/(R1+R2).
- Used for: analog sensors, level shifting, reference voltages.

PULL-UP / PULL-DOWN RESISTOR:
- Pull-up: Resistor (10K typical) from signal line to VCC. Default state = HIGH.
- Pull-down: Resistor (10K typical) from signal line to GND. Default state = LOW.
- Used with buttons, open-collector outputs, I2C lines.

BUTTON/SWITCH:
- One terminal to digital pin, other terminal to GND. Enable internal pull-up (INPUT_PULLUP).
- OR: One terminal to digital pin (with external pull-down 10K to GND), other terminal to VCC.

H-BRIDGE (for motor direction control):
- 4 transistors/MOSFETs arranged to allow current flow in either direction through motor.
- L293D IC implements this in a single chip.

RC FILTER:
- Low-pass: Resistor in series, Capacitor to GND. Cutoff = 1/(2*pi*R*C).
- High-pass: Capacitor in series, Resistor to GND.

TRANSISTOR SWITCH:
- Arduino pin -> 1K resistor -> Base of NPN. Collector to load+, load- to VCC. Emitter to GND.
- Flyback diode across inductive loads (motors, relays).

CURRENT LIMITING:
- R = (Vsource - Vforward) / Idesired.
- For LED on 5V: R = (5-2)/0.02 = 150 ohm. Use 220 ohm for safety.
- For LED on 3.3V: R = (3.3-2)/0.02 = 65 ohm. Use 100 ohm for safety.

DECOUPLING:
- 100nF ceramic capacitor between VCC and GND, as close to IC power pins as possible.
- Prevents high-frequency noise from affecting IC operation.
"""

ADVANCED_MODULES = """
ADVANCED MODULES AND BREAKOUT BOARDS:

L298N MOTOR DRIVER MODULE:
- ENA, ENB: PWM speed control for motor A and B.
- IN1, IN2: Direction control for motor A (HIGH/LOW = direction).
- IN3, IN4: Direction control for motor B.
- 12V: Motor power input (7-35V). 5V: Logic power (or 5V output if jumper is set).
- GND: Common ground with Arduino.

OLED DISPLAY (SSD1306, 0.96" I2C):
- 4 pins: VCC=3.3-5V, GND, SDA=A4, SCL=A5.
- I2C address: usually 0x3C or 0x3D.
- Library: Adafruit_SSD1306 + Adafruit_GFX.

7-SEGMENT DISPLAY (common cathode):
- 7 segment pins (a-g) + decimal point (dp). Common pin to GND.
- Each segment needs current-limiting resistor (220-330 ohm).
- For multiplexed 4-digit: use 74HC595 shift register or MAX7219 driver.

MAX7219 LED DRIVER:
- 5 pins: VCC=5V, GND, DIN=digital pin, CS=digital pin, CLK=digital pin.
- Controls up to 8 digits of 7-segment display or 8x8 LED matrix.

STEPPER MOTOR (28BYJ-48 with ULN2003 driver):
- Driver has IN1-IN4 pins connected to 4 Arduino digital pins.
- Motor connects to driver board via 5-pin connector.
- Powered from 5V (can draw 500mA+, use external supply).

NEMA 17 STEPPER (with A4988/DRV8825):
- STEP pin: pulse for each step. DIR pin: HIGH/LOW for direction.
- VMOT: Motor power (8-35V). GND: Common ground.
- ENABLE: Active LOW (pull LOW to enable, HIGH to disable).
- MS1, MS2, MS3: Microstepping selection.

NRF24L01 WIRELESS MODULE:
- 8 pins: VCC=3.3V (NOT 5V!), GND, CE=digital, CSN=digital, SCK=13, MOSI=11, MISO=12.
- Needs 10uF capacitor across VCC and GND for stability.

DS1307/DS3231 RTC MODULE (I2C):
- 4 pins: VCC=5V, GND, SDA=A4, SCL=A5.
- Has backup battery (CR2032) for timekeeping when power is off.

SD CARD MODULE (SPI):
- 6 pins: VCC=5V, GND, CS=digital pin (usually 4 or 10), MOSI=11, MISO=12, SCK=13.

IR RECEIVER (TSOP38238):
- 3 pins: OUT=digital pin, GND, VCC=5V.
- Receives 38kHz modulated IR signals from remote controls.

JOYSTICK MODULE:
- 5 pins: VCC=5V, GND, VRx=analog pin, VRy=analog pin, SW=digital pin (button, needs pull-up).

ROTARY ENCODER:
- 5 pins: CLK=digital, DT=digital, SW=digital (button), VCC=5V, GND.
- CLK and DT need pull-up resistors or INPUT_PULLUP.
"""

DEBUGGING_METHODOLOGY = """
SYSTEMATIC DEBUGGING APPROACH:

1. POWER CHECK:
   - Is the MCU powered? Look for power LED on the board.
   - Are power rails connected? 5V to + rail, GND to - rail.
   - Is the breadboard power rail split at the midpoint? Bridge it if needed.
   - Is voltage correct? 3.3V components on 5V can be damaged.

2. GROUND CHECK:
   - Every circuit MUST have a complete ground return path.
   - The most common error is a missing GND connection.
   - All GND pins must connect to the same ground rail.

3. CONNECTION TRACING:
   - For each component, trace the path from VCC through the component to GND.
   - Verify that series components share a breadboard row.
   - Verify that parallel components each have their own path to VCC and GND.

4. COMPONENT VALIDATION:
   - Is the component in the right orientation? (LED polarity, capacitor polarity, IC pin 1)
   - Is the component value correct? (resistor color code, capacitor marking)
   - Is the component functioning? (test with multimeter if possible)

5. SIGNAL PATH:
   - Which MCU pin is the signal coming from?
   - Is the signal digital or analog? PWM or plain HIGH/LOW?
   - Does the signal reach the component? Trace the wire path.

6. COMMON MISTAKES:
   - Components on opposite sides of breadboard gap (not connected)
   - Wrong breadboard row (off by one)
   - Power rail not connected to MCU power pins
   - Missing pull-up/pull-down resistor on button or I2C
   - LED without current-limiting resistor
   - Motor/relay connected directly to MCU pin (needs transistor/driver)
   - ESP32/3.3V device on 5V rail
   - IC inserted backwards (pin 1 in wrong position)

ELECTRICAL FORMULAS:
- Ohm's Law: V = I * R, I = V / R, R = V / I
- Power: P = V * I = V^2 / R = I^2 * R
- Resistors in series: Rtotal = R1 + R2 + R3...
- Resistors in parallel: 1/Rtotal = 1/R1 + 1/R2 + 1/R3...
- Voltage divider: Vout = Vin * R2 / (R1 + R2)
- LED current: I = (Vsource - Vled) / R
- Capacitor charge time: T = R * C (time constant), 5*RC for full charge
- 555 timer frequency: f = 1.44 / ((R1 + 2*R2) * C)
"""

def get_full_knowledge_base():
    """Return the complete knowledge base as a single string."""
    return (BREADBOARD_KNOWLEDGE + ARDUINO_KNOWLEDGE + COMPONENT_KNOWLEDGE +
            IC_KNOWLEDGE + CIRCUIT_PATTERNS + ADVANCED_MODULES +
            DEBUGGING_METHODOLOGY)

def get_component_safety_rules(component_type: str) -> str:
    """Return specific safety rules for a component type."""
    rules = {
        "led": "ALWAYS needs a resistor in series (typically 220-330 ohm for 5V, 100-150 ohm for 3.3V).",
        "capacitor": "Electrolytic (cylindrical, with stripe): HAS POLARITY. Stripe/shorter leg = negative. WRONG POLARITY CAN EXPLODE.",
        "motor": "NEVER connect directly to Arduino pin (draws too much current). Use a transistor (NPN + flyback diode) or motor driver.",
        "relay": "Load side can have high voltage. Always use flyback diode on the coil."
    }
    return rules.get(component_type.lower(), "No specific safety rules found.")
