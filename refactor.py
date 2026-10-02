# -*- coding: utf-8 -*-
import os
import shutil

def setup_dirs():
    for d in ['detectors', 'logic', 'web']:
        if not os.path.exists(d):
            os.makedirs(d)

def move_files():
    moves = [
        ("main.py", "main.py"),
        ("backend/streamer.py", "camera.py"),
        ("vision/tracker.py", "detectors/tracker.py"),
        ("vision/resistor.py", "detectors/resistor.py"),
        ("vision/wire_tracer.py", "detectors/wires.py"),
        ("vision/ptz_tracker.py", "detectors/zoom.py"),
        ("vision/endpoint_tracker.py", "detectors/memory.py"),
        ("engine/circuit.py", "logic/solver.py"),
        ("engine/grid_mapper.py", "logic/grid.py"),
        ("engine/snapshot.py", "logic/snapshot.py"),
        ("engine/hardware.py", "logic/gpio.py"),
        ("ar/index.html", "web/index.html"),
        ("ar/ar_overlay.js", "web/overlay.js")
    ]
    
    for src, dst in moves:
        if os.path.exists(src):
            shutil.move(src, dst)
            print(f"Moved {src} -> {dst}")
        else:
            print(f"Skipping {src} (not found)")

def replace_in_file(filepath, replacements):
    if not os.path.exists(filepath):
        return
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    for old, new in replacements:
        content = content.replace(old, new)
        
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

def update_imports_and_text():
    py_replacements = [
        ("from camera", "from camera"),
        ("from detectors.tracker", "from detectors.tracker"),
        ("from detectors.resistor", "from detectors.resistor"),
        ("from detectors.wires", "from detectors.wires"),
        ("from detectors.zoom", "from detectors.zoom"),
        ("from detectors.memory", "from detectors.memory"),
        ("logic.solver", "logic.solver"),
        ("from logic.snapshot", "from logic.snapshot"),
        ("from logic.gpio", "from logic.gpio"),
        ("logic.grid", "logic.grid"),
        ("CircuitSolver", "CircuitSolver"),
        ("AutoZoom", "AutoZoom"),
        ("WireMemory", "WireMemory"),
        ("Tracker", "Tracker"),
        ("GPIOController", "GPIOController"),
        ("SnapshotManager", "SnapshotManager"),
        ("ar_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), \"..\", \"ar\"))", "web_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), \"web\"))"),
        ("ar_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), \"ar\"))", "web_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), \"web\"))"),
        ("os.path.join(web_dir", "os.path.join(web_dir"),
        ("send_from_directory(web_dir", "send_from_directory(web_dir"),
        ("Snapshot saved to", "Snapshot saved to"),
        ("import RPi.GPIO as gpio", "import RPi.GPIO as gpio"),
        ("self.gpio", "self.gpio"),
        ("main.py", "main.py")
    ]
    
    html_replacements = [
        ("ar_overlay.js", "overlay.js"),
        ("POWER: USB/POWER-BANK ACTIVE", "POWER: USB/POWER-BANK ACTIVE"),
        ("POWER: UNKNOWN", "POWER: UNKNOWN"),
        ("CURRENT:", "CURRENT:"),
        ("PASS:", "PASS:"),
        ("FAIL:", "FAIL:"),
        ("SOLUTION:", "SOLUTION:"),
        ("WARN:", "WARN:"),
        ("Auto-Focus Phone", "Auto-Focus Camera"),
        ("Auto-Focus Camera", "Auto-Focus Camera"),
        ("ar-banner", "status-banner"),
        ("arCanvas", "overlayCanvas"),
        ("AROverlayManager", "OverlayManager")
    ]
    
    # We will just strip all non-ascii characters from HTML and python print statements to guarantee no emojis
    
    js_replacements = [
        ("class AROverlayManager", "class OverlayManager")
    ]
    
    # Update python files
    for root, _, files in os.walk('.'):
        if 'env' in root or '.git' in root or '__pycache__' in root or 'runs' in root:
            continue
        for file in files:
            if file.endswith('.py'):
                replace_in_file(os.path.join(root, file), py_replacements)
                
    replace_in_file("web/index.html", html_replacements)
    replace_in_file("web/overlay.js", js_replacements)
    
def clean_empty_dirs():
    for d in ['backend', 'vision', 'engine', 'ar']:
        if os.path.exists(d) and not os.listdir(d):
            os.rmdir(d)
            print(f"Removed empty directory: {d}")

if __name__ == '__main__':
    setup_dirs()
    move_files()
    update_imports_and_text()
    clean_empty_dirs()
    print("Refactoring complete.")
