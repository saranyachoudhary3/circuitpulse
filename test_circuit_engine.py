import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "pi_transfer"))
from circuit_engine import CircuitEngine


def run_tests():
    engine = CircuitEngine()
    print("Testing 100% Automatic Circuit Logic & Verification Engine...\n")

    valid_detections = [
        {"class": "arduino_uno", "confidence": 0.85, "bbox": {"x1": 100, "y1": 100, "x2": 300, "y2": 400}},
        {"class": "breadboard", "confidence": 0.90, "bbox": {"x1": 350, "y1": 100, "x2": 600, "y2": 400}},
        {"class": "resistor", "confidence": 0.75, "bbox": {"x1": 120, "y1": 110, "x2": 380, "y2": 150}},
        {"class": "led", "confidence": 0.80, "bbox": {"x1": 380, "y1": 150, "x2": 400, "y2": 180}},
    ]
    report = engine.verify(valid_detections)
    print("Test 1 (Auto-Detected Valid Circuit):")
    print(f"  Circuit: {report['circuit_name']}")
    print(f"  Status: {report['status']}")
    print(f"  Errors: {len(report['errors'])}")
    assert "Arduino" in report["circuit_name"]
    assert report["status"] == "PASS"
    assert len(report["errors"]) == 0

    pin7_detections = [
        {"class": "arduino_uno", "confidence": 0.85, "bbox": {"x1": 100, "y1": 100, "x2": 300, "y2": 400}},
        {"class": "breadboard", "confidence": 0.90, "bbox": {"x1": 350, "y1": 100, "x2": 600, "y2": 400}},
        {"class": "resistor", "confidence": 0.75, "ohms": 220, "resistance": "220Ω ±5%", "bbox": {"x1": 400, "y1": 200, "x2": 450, "y2": 250}},
        {"class": "led", "confidence": 0.80, "bbox": {"x1": 460, "y1": 200, "x2": 480, "y2": 220}},
        {"class": "wire", "confidence": 0.75, "bbox": {"x1": 245, "y1": 120, "x2": 400, "y2": 200}},
    ]
    report_pin7 = engine.verify(pin7_detections)
    print("\nTest 2 (Wire in Pin 7, Expected at Pin 15):")
    print(f"  Circuit: {report_pin7['circuit_name']}")
    print(f"  Status: {report_pin7['status']}")
    print(f"  Errors: {[e['message'] for e in report_pin7['errors']]}")
    assert report_pin7["status"] == "FAULT_DETECTED"
    err_pin7 = [e for e in report_pin7["errors"] if e["type"] == "wrong_pin"][0]
    print(f"  Message: {err_pin7.get('message')}")
    print(f"  Remedy Guidance: {err_pin7.get('remedy')}")
    print(f"  Spoken TTS Advice: {err_pin7.get('tts')}")
    assert err_pin7["message"] == "Wrong pin: wire at Arduino pin 7, must be at pin 15"
    assert err_pin7["remedy"] == "Move wire from Arduino pin 7 to pin 15"
    assert err_pin7["tts"] == "Fault detected: Wire is at Arduino pin 7 but should be at pin 15. Solution: Move the wire from pin 7 to pin 15."

    pin15_detections = [
        {"class": "arduino_uno", "confidence": 0.85, "bbox": {"x1": 100, "y1": 100, "x2": 300, "y2": 400}},
        {"class": "breadboard", "confidence": 0.90, "bbox": {"x1": 350, "y1": 100, "x2": 600, "y2": 400}},
        {"class": "resistor", "confidence": 0.75, "ohms": 220, "resistance": "220Ω ±5%", "bbox": {"x1": 400, "y1": 200, "x2": 450, "y2": 250}},
        {"class": "led", "confidence": 0.80, "bbox": {"x1": 460, "y1": 200, "x2": 480, "y2": 220}},
        {"class": "wire", "confidence": 0.85, "bbox": {"x1": 130, "y1": 120, "x2": 400, "y2": 200}},
    ]
    report_pin15 = engine.verify(pin15_detections)
    print("\nTest 3 (Wire Corrected from Pin 7 to Pin 15 - Reverified OK):")
    print(f"  Circuit: {report_pin15['circuit_name']}")
    print(f"  Status: {report_pin15['status']}")
    print(f"  Errors: {len(report_pin15['errors'])}")
    assert report_pin15["status"] == "PASS"
    assert len(report_pin15["errors"]) == 0

    missing_resistor = [
        {"class": "arduino_uno", "confidence": 0.85, "bbox": {"x1": 100, "y1": 100, "x2": 300, "y2": 400}},
        {"class": "breadboard", "confidence": 0.90, "bbox": {"x1": 350, "y1": 100, "x2": 600, "y2": 400}},
        {"class": "led", "confidence": 0.80, "bbox": {"x1": 380, "y1": 150, "x2": 400, "y2": 180}},
    ]
    report2 = engine.verify(missing_resistor)
    print("\nTest 4 (Missing Resistor):")
    print(f"  Circuit: {report2['circuit_name']}")
    print(f"  Status: {report2['status']}")
    print(f"  Errors: {[e['message'] for e in report2['errors']]}")
    assert report2["status"] == "FAULT_DETECTED"
    assert any("resistor" in e["message"].lower() for e in report2["errors"])

    wrong_pin_detections = [
        {"class": "arduino_uno", "confidence": 0.85, "bbox": {"x1": 100, "y1": 100, "x2": 300, "y2": 400}},
        {"class": "breadboard", "confidence": 0.90, "bbox": {"x1": 350, "y1": 100, "x2": 600, "y2": 400}},
        {"class": "resistor", "confidence": 0.75, "bbox": {"x1": 400, "y1": 200, "x2": 450, "y2": 250}},
        {"class": "led", "confidence": 0.80, "bbox": {"x1": 460, "y1": 200, "x2": 480, "y2": 220}},
        {"class": "wire", "confidence": 0.70, "bbox": {"x1": 215, "y1": 110, "x2": 400, "y2": 200}},
    ]
    report3 = engine.verify(wrong_pin_detections)
    print("\nTest 5 (Pin 8 Mismatch):")
    print(f"  Circuit: {report3['circuit_name']}")
    print(f"  Status: {report3['status']}")
    print(f"  Errors: {[e['message'] for e in report3['errors']]}")
    assert report3["status"] == "FAULT_DETECTED"
    err_pin = [e for e in report3["errors"] if e["type"] == "wrong_pin"][0]
    assert err_pin["message"] == "Wrong pin: wire at Arduino D8, must be at D13"

    short_detections = [
        {"class": "arduino_uno", "confidence": 0.85, "bbox": {"x1": 100, "y1": 100, "x2": 300, "y2": 400}},
        {"class": "breadboard", "confidence": 0.90, "bbox": {"x1": 350, "y1": 100, "x2": 600, "y2": 400}},
        {"class": "wire", "confidence": 0.88, "bbox": {"x1": 130, "y1": 380, "x2": 180, "y2": 385}},
    ]
    report4 = engine.verify(short_detections)
    print("\nTest 4 (Auto-Detected Critical Short Circuit):")
    print(f"  Circuit: {report4['circuit_name']}")
    print(f"  Status: {report4['status']}")
    print(f"  Errors: {[e['message'] for e in report4['errors']]}")
    assert report4["status"] == "FAULT_DETECTED"
    assert any("short circuit" in e["message"].lower() for e in report4["errors"])

    wrong_resistor_value = [
        {"class": "arduino_uno", "confidence": 0.85, "bbox": {"x1": 100, "y1": 100, "x2": 300, "y2": 400}},
        {"class": "breadboard", "confidence": 0.90, "bbox": {"x1": 350, "y1": 100, "x2": 600, "y2": 400}},
        {"class": "resistor", "confidence": 0.80, "ohms": 10000, "resistance": "10kΩ ±5%", "bbox": {"x1": 120, "y1": 110, "x2": 380, "y2": 150}},
        {"class": "led", "confidence": 0.80, "bbox": {"x1": 380, "y1": 150, "x2": 400, "y2": 180}},
    ]
    report5 = engine.verify(wrong_resistor_value)
    print("\nTest 5 (Auto-Detected Incorrect Resistor Value):")
    print(f"  Circuit: {report5['circuit_name']}")
    print(f"  Status: {report5['status']}")
    print(f"  Errors: {[e['message'] for e in report5['errors']]}")
    assert report5["status"] == "FAULT_DETECTED"
    assert any("resistor" in e["message"].lower() for e in report5["errors"])
    err_res = [e for e in report5["errors"] if e["type"] == "resistor_value_mismatch"][0]
    print(f"  Remedy Guidance: {err_res.get('remedy')}")
    print(f"  Spoken TTS Advice: {err_res.get('tts')}")
    assert "220" in err_res.get("remedy", "")

    hw_defect_detections = [
        {"class": "arduino_uno", "confidence": 0.85, "bbox": {"x1": 100, "y1": 100, "x2": 300, "y2": 400}},
        {"class": "breadboard", "confidence": 0.90, "bbox": {"x1": 350, "y1": 100, "x2": 600, "y2": 400}},
        {"class": "short", "confidence": 0.88, "bbox": {"x1": 200, "y1": 250, "x2": 240, "y2": 290}},
    ]
    report6 = engine.verify(hw_defect_detections)
    print("\nTest 6 (Auto-Detected Physical Hardware Defect):")
    print(f"  Circuit: {report6['circuit_name']}")
    print(f"  Status: {report6['status']}")
    print(f"  Errors: {[e['message'] for e in report6['errors']]}")
    assert report6["status"] == "FAULT_DETECTED"
    assert any("defect" in e["message"].lower() or "hardware" in e["message"].lower() for e in report6["errors"])

    corrected_wire_detections = [
        {"class": "arduino_uno", "confidence": 0.85, "bbox": {"x1": 100, "y1": 100, "x2": 300, "y2": 400}},
        {"class": "breadboard", "confidence": 0.90, "bbox": {"x1": 350, "y1": 100, "x2": 600, "y2": 400}},
        {"class": "resistor", "confidence": 0.75, "ohms": 220, "resistance": "220Ω ±5%", "bbox": {"x1": 400, "y1": 200, "x2": 450, "y2": 250}},
        {"class": "led", "confidence": 0.80, "bbox": {"x1": 460, "y1": 200, "x2": 480, "y2": 220}},
        {"class": "wire", "confidence": 0.85, "bbox": {"x1": 135, "y1": 140, "x2": 400, "y2": 200}},
    ]
    report7 = engine.verify(corrected_wire_detections)
    print("\nTest 7 (Wire Moved into Correct Pin 13 - Changes Implemented):")
    print(f"  Circuit: {report7['circuit_name']}")
    print(f"  Status: {report7['status']}")
    print(f"  Errors: {len(report7['errors'])}")
    assert report7["status"] == "PASS"
    assert len(report7["errors"]) == 0

    print("\n[ALL 7 AUTOMATIC DETECTION TESTS PASSED SUCCESSFULLY]")


if __name__ == "__main__":
    run_tests()
