import os

path = r'c:\Users\Ayushman\Desktop\circuit_pulse\engine\circuit.py'
with open(path, 'r') as f:
    code = f.read()

# 1. Update the method signature
code = code.replace('def verify(self, detections, frame_width=640, frame_height=480):', 
                    'def verify(self, detections, frame=None, frame_width=640, frame_height=480):')

# 2. Add the _is_mcu_powered method if it doesn't exist
if '_is_mcu_powered' not in code:
    helper = '''
    def _is_mcu_powered(self, crop):
        if crop is None or crop.size == 0:
            return False
        import cv2
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        # Colored LED (e.g. Red, Green, Blue)
        mask1 = cv2.inRange(hsv, (0, 60, 220), (179, 255, 255))
        # Pure white / Hot center of an LED
        mask2 = cv2.inRange(hsv, (0, 0, 245), (179, 40, 255))
        import numpy as np
        mask = cv2.bitwise_or(mask1, mask2)
        bright_count = cv2.countNonZero(mask)
        # Require at least 6 bright pixels to avoid random glare
        return bright_count > 6

    def verify(self,'''
    code = code.replace('    def verify(self,', helper.strip() + '\n    def verify(self,')

# 3. Update the tutor logic block to use the frame for LED detection
old_tutor_logic = '''
        # --- CIRCUIT TUTOR STATE MACHINE ---
        # The AI guides the user step-by-step.
        has_mcu = any(d['class'].lower() in ['arduino_uno', 'arduino_nano', 'arduino_mega', 'esp32'] for d in detections)
        has_power = any(d['class'].lower() == 'power_bank' for d in detections)
'''

new_tutor_logic = '''
        # --- CIRCUIT TUTOR STATE MACHINE ---
        # The AI guides the user step-by-step.
        mcu_boxes = [d for d in detections if d['class'].lower() in ['arduino_uno', 'arduino_nano', 'arduino_mega', 'esp32']]
        has_mcu = len(mcu_boxes) > 0
        
        is_powered = False
        if has_mcu and frame is not None:
            mb = mcu_boxes[0]['bbox']
            # Crop to the MCU with safe bounds
            crop = frame[max(0, mb['y1']):min(frame_height, mb['y2']), max(0, mb['x1']):min(frame_width, mb['x2'])]
            is_powered = self._is_mcu_powered(crop)
            
        has_power = is_powered
'''
code = code.replace(old_tutor_logic.strip(), new_tutor_logic.strip())

# 4. Update the logic for Step 1
old_step_1 = '''
        if has_mcu and has_power:
            steps[0]['done'] = True
            step_index = 1
'''
new_step_1 = '''
        if has_mcu:
            if has_power:
                steps[0]['done'] = True
                step_index = 1
            else:
                steps[0]['title'] = 'STEP 1: Plug in the Board'
                steps[0]['desc'] = 'Microcontroller detected, but it is NOT powered on. Please plug in the USB!'
'''
code = code.replace(old_step_1.strip(), new_step_1.strip())

# 5. Inject is_powered into the returned dictionary
code = code.replace("'tutor_mode': True,", "'tutor_mode': True,\n                'is_powered': is_powered,")
code = code.replace("'tutor_mode': False", "'tutor_mode': False,\n                'is_powered': False")

with open(path, 'w') as f:
    f.write(code)
