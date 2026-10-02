import os
import re

app_path = r'c:\Users\Ayushman\Desktop\circuit_pulse\backend\app.py'
with open(app_path, 'r') as f:
    code = f.read()

# Add model_power variable
code = code.replace('model_passives = None', 'model_passives = None\nmodel_power = None')

# Add loading logic for model_power
load_logic = """
    print("Loading backend vision models...")
    model_main = _pick("base_ncnn_model", "main")
    model_passives = _pick("passives_ncnn_model", "passives")
    
    power_pt_path = os.path.join(repo_root, "yolov8n.pt")
    power_ncnn_path = os.path.join(repo_root, "yolov8n_ncnn_model")
    if os.path.exists(power_ncnn_path):
        model_power = YOLO(power_ncnn_path, task="detect")
    elif os.path.exists(power_pt_path):
        model_power = YOLO(power_pt_path)
"""
code = code.replace('print("Loading backend vision models...")\n    model_main = _pick("base_ncnn_model", "main")\n    model_passives = _pick("passives_ncnn_model", "passives")', load_logic.strip())

# Run inference with model_power
infer_logic = """
            if model_main and model_passives:
                d_pass = run_inference(model_passives, frame)
                d_main_raw = run_inference(model_main, frame)
                d_main = [b for b in d_main_raw if b["class"].lower() in {"arduino_uno", "arduino_nano", "arduino_mega", "esp32", "breadboard", "led"}]
                
                d_power = []
                if model_power:
                    d_p_raw = run_inference(model_power, frame)
                    for b in d_p_raw:
                        cls_name = b["class"].lower()
                        if cls_name in ["cell phone", "remote", "laptop"]:
                            b["class"] = "power_bank"
                            d_power.append(b)
                            break
                
                merged = deduplicate_and_merge_wires(d_pass + d_main + d_power)
                raw_detections = filter_detections(merged, w, h, full_frame=frame)
"""
code = re.sub(r'if model_main and model_passives:[\s\S]*?raw_detections = filter_detections\(merged, w, h, full_frame=frame\)', infer_logic.strip(), code)

# Ensure ALLOWED_CLASSES has power_bank
code = code.replace('"resistor", "wire", "led"', '"resistor", "wire", "led", "power_bank"')

with open(app_path, 'w') as f:
    f.write(code)
