import os

path = r'c:\Users\Ayushman\Desktop\circuit_pulse\engine\circuit.py'
with open(path, 'r') as f:
    lines = f.readlines()

new_lines = []
skip_verify_body = False
in_verify = False

for line in lines:
    if 'def verify(' in line:
        in_verify = True
        new_lines.append(line)
        continue
        
    if in_verify:
        if 'now_time = time.time()' in line:
            # We are inside verify. Inject the complete new logic and skip the rest until return
            new_lines.append(line)
            new_lines.append('''
        if not detections:
            return {
                "status": "PASS",
                "circuit_id": "scanning",
                "circuit_name": "Scanning...",
                "mcu_info": "",
                "errors": [],
                "warnings": [],
                "tts": "",
                "tutor_mode": False
            }

        # --- CIRCUIT TUTOR STATE MACHINE ---
        # The AI guides the user step-by-step.
        has_mcu = any(d['class'].lower() in ['arduino_uno', 'arduino_nano', 'arduino_mega', 'esp32'] for d in detections)
        has_power = any(d['class'].lower() == 'power_bank' for d in detections)
        has_bb = any(d['class'].lower() == 'breadboard' for d in detections)
        
        leds = [d for d in detections if d['class'].lower() == 'led']
        resistors = [d for d in detections if d['class'].lower() == 'resistor']
        wires = [d for d in detections if d['class'].lower() == 'wire']
        bb_boxes = [d for d in detections if d['class'].lower() == 'breadboard']
        
        led_on_bb = False
        resistor_on_bb = False
        
        if bb_boxes and leds:
            led_on_bb = any(self._check_overlap(led['bbox'], bb_boxes[0]['bbox']) for led in leds)
        if bb_boxes and resistors:
            resistor_on_bb = any(self._check_overlap(res['bbox'], bb_boxes[0]['bbox']) for res in resistors)
            
        mcu_wired = False
        circuit_complete = False
        
        if len(wires) >= 2 and led_on_bb and resistor_on_bb and has_mcu:
            mcu_wired = True
            circuit_complete = True
            
        step_index = 0
        steps = [
            {'title': 'STEP 1: Power & Controller', 'desc': 'Place the Microcontroller and the Power Bank in the camera view.', 'done': False},
            {'title': 'STEP 2: Breadboard Base', 'desc': 'Place the Breadboard in the camera view.', 'done': False},
            {'title': 'STEP 3: Add the LED', 'desc': 'Insert the LED firmly into the Breadboard holes.', 'done': False},
            {'title': 'STEP 4: Add the Resistor', 'desc': 'Insert the Resistor into the Breadboard in series with the LED.', 'done': False},
            {'title': 'STEP 5: Wiring the Circuit', 'desc': 'Connect jumper wires from the Microcontroller to the Resistor, and from the LED to GND.', 'done': False}
        ]
        
        if has_mcu and has_power:
            steps[0]['done'] = True
            step_index = 1
            if has_bb:
                steps[1]['done'] = True
                step_index = 2
                if led_on_bb:
                    steps[2]['done'] = True
                    step_index = 3
                    if resistor_on_bb:
                        steps[3]['done'] = True
                        step_index = 4
                        if mcu_wired and circuit_complete:
                            steps[4]['done'] = True
                            step_index = 5
                            
        pending_steps = [s for s in steps if not s['done']]
        
        cmcu = "ESP32/Arduino" if has_mcu else "Awaiting MCU"
        
        if step_index == 5:
            return {
                'status': 'PASS',
                'circuit_id': 'led_blink',
                'circuit_name': 'Basic LED Circuit',
                'mcu_info': cmcu,
                'circuit_concept': 'Completed Circuit.',
                'errors': [],
                'warnings': [],
                'tts': 'Circuit is complete and working correctly.',
                'tutor_mode': True,
                'current_step': None,
                'pending_steps': []
            }
        else:
            current_step = pending_steps[0]
            
            # If everything is completely empty, don't scream errors, just return scanning
            if not has_mcu and not has_bb and not leds and not has_power:
                return {
                    'status': 'PASS',
                    'circuit_id': 'led_blink',
                    'circuit_name': 'Basic LED Circuit',
                    'mcu_info': cmcu,
                    'circuit_concept': 'Building Circuit Step-by-Step',
                    'errors': [],
                    'warnings': [],
                    'tts': '',
                    'tutor_mode': True,
                    'current_step': current_step,
                    'pending_steps': pending_steps[1:]
                }

            return {
                'status': 'FAULT_DETECTED',
                'circuit_id': 'led_blink',
                'circuit_name': 'Basic LED Circuit',
                'mcu_info': cmcu,
                'circuit_concept': 'Building Circuit Step-by-Step',
                'errors': [{
                    'message': current_step['title'],
                    'remedy': current_step['desc']
                }],
                'warnings': [],
                'tts': current_step['desc'],
                'tutor_mode': True,
                'current_step': current_step,
                'pending_steps': pending_steps[1:]
            }

    def _dummy_to_skip_rest(self):
''')
            skip_verify_body = True
            continue
            
    if skip_verify_body:
        # We need to skip all lines until the next method definition
        if line.startswith('    def ') and not line.startswith('    def verify('):
            skip_verify_body = False
            in_verify = False
            new_lines.append(line)
        continue
        
    new_lines.append(line)

with open(path, 'w') as f:
    f.writelines(new_lines)
