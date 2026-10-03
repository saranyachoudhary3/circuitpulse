"""Conservative Arduino/ESP32 source inspection for hardware/firmware mismatch."""

from __future__ import annotations

import re
from typing import Any


PIN_MODE = re.compile(r"\bpinMode\s*\(\s*([A-Za-z0-9_]+)\s*,\s*(INPUT_PULLUP|INPUT_PULLDOWN|INPUT|OUTPUT_OPEN_DRAIN|OUTPUT)\s*\)")
DIGITAL_WRITE = re.compile(r"\bdigitalWrite\s*\(\s*([A-Za-z0-9_]+)\s*,\s*(HIGH|LOW)\s*\)")
PWM_WRITE = re.compile(r"\b(?:analogWrite|ledcWrite)\s*\(\s*([A-Za-z0-9_]+)\s*,\s*([0-9]+)\s*\)")
SERIAL_BEGIN = re.compile(r"\bSerial\w*\.begin\s*\(\s*(\d+)")
PIN_DEFINE = re.compile(r"(?m)^\s*(?:#define\s+|(?:const|constexpr)\s+(?:uint\d+_t|int)\s+)([A-Za-z_]\w*)\s*(?:=\s*)?([A-Za-z0-9_]+)")

_LINE_COMMENT = re.compile(r"//[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _strip_comments(source: str) -> str:
    """Remove C/C++ comments before regex parsing.

    Prevents commented-out code like ``// pinMode(13, OUTPUT)`` from
    being parsed as live pin configuration.
    """
    source = _BLOCK_COMMENT.sub("", source)
    source = _LINE_COMMENT.sub("", source)
    return source


def analyze_firmware(source: str) -> dict[str, Any]:
    """Extract only explicit, statically visible hardware intent.

    Dynamic pin expressions are intentionally not guessed; callers can display
    the returned limitations and request a user-provided pin map.
    """
    if not isinstance(source, str) or not source.strip():
        raise ValueError("Firmware source must be a non-empty string.")
    source = _strip_comments(source)
    aliases = {name: value for name, value in PIN_DEFINE.findall(source)}

    def resolve(pin: str) -> str:
        # Resolve one literal alias only; recursive/dynamic expressions remain
        # visible in limitations instead of being guessed.
        return aliases.get(pin, pin)

    modes = {resolve(pin): mode for pin, mode in PIN_MODE.findall(source)}
    writes = {resolve(pin): level for pin, level in DIGITAL_WRITE.findall(source)}
    pwm = {resolve(pin): int(value) for pin, value in PWM_WRITE.findall(source)}
    known = set(modes) | set(writes) | set(pwm)
    i2c = "Wire.begin" in source
    spi = "SPI.begin" in source
    serial_baud = [int(value) for value in SERIAL_BEGIN.findall(source)]
    return {
        "pins": {pin: {"mode": modes.get(pin), "digital_write": writes.get(pin), "pwm": pwm.get(pin)} for pin in sorted(known)},
        "protocols": {"i2c": i2c, "spi": spi, "serial_baud": serial_baud},
        "limitations": ["Only literal pinMode/digitalWrite/analogWrite/ledcWrite calls and one-level literal pin aliases are statically analyzed."],
    }


def verify_firmware_against_preset(analysis: dict[str, Any], preset: dict[str, Any]) -> list[dict[str, Any]]:
    """Find clear pin/protocol contradictions without inferring runtime behavior."""
    findings: list[dict[str, Any]] = []
    pins = analysis.get("pins", {})
    for connection in preset.get("connections", []):
        for position, endpoint in (("from", connection["from"]), ("to", connection["to"])):
            if not endpoint.startswith("arduino:D"):
                continue
            pin = endpoint.split(":", 1)[1]
            observed = pins.get(pin)
            # Blueprint convention: Arduino terminal on a connection's source
            # side is an output. On the destination side it may be an input.
            if observed and observed["mode"] == "INPUT" and position == "from":
                findings.append({"code": "FIRMWARE_PIN_MODE_CONFLICT", "severity": "error",
                                 "message": f"Firmware configures {pin} as INPUT but the blueprint uses it as an output.",
                                 "evidence": {"pin": pin, "connection": connection["id"]}})
    if "i2c" in preset.get("id", "") and not analysis.get("protocols", {}).get("i2c"):
        findings.append({"code": "FIRMWARE_I2C_NOT_INITIALIZED", "severity": "warning",
                         "message": "The selected I2C blueprint has no visible Wire.begin call.", "evidence": {}})
    return findings


def verify_firmware_contract(source: str, rule: dict[str, Any], circuit) -> list[dict[str, Any]]:
    """Compare statically visible firmware intent with reviewed rules and trace.

    A source file alone is not execution proof. This function can additionally
    compare literal output intent with the final captured analyzer level only
    when the rule explicitly maps firmware pins to reviewed circuit nets.
    """
    analysis, findings = analyze_firmware(source), []
    expected_pins = rule.get("expected_pins", {})
    if not isinstance(expected_pins, dict):
        raise ValueError("firmware expected_pins must be an object.")
    for pin, expectation in expected_pins.items():
        if not isinstance(pin, str) or not isinstance(expectation, dict):
            raise ValueError("firmware expected_pins entries need pin names and expectation objects.")
        observed = analysis["pins"].get(pin)
        if observed is None:
            findings.append(_finding("FIRMWARE_PIN_UNDECLARED", "warning", f"Firmware has no statically visible configuration for {pin}.", {"pin": pin}))
            continue
        if "mode" in expectation and observed["mode"] != expectation["mode"]:
            findings.append(_finding("FIRMWARE_PIN_MODE_MISMATCH", "error", f"Firmware pin {pin} mode differs from the reviewed requirement.",
                                     {"pin": pin, "expected": expectation["mode"], "actual": observed["mode"]}))
        if expectation.get("require_pwm") and observed["pwm"] is None:
            findings.append(_finding("FIRMWARE_PWM_MISSING", "error", f"Firmware does not visibly drive required PWM pin {pin}.", {"pin": pin}))
    for protocol, expected in rule.get("required_protocols", {}).items():
        if not isinstance(expected, bool):
            raise ValueError("required_protocols values must be boolean.")
        if analysis["protocols"].get(protocol) is not expected:
            findings.append(_finding("FIRMWARE_PROTOCOL_MISMATCH", "error", f"Firmware protocol {protocol} does not match the reviewed requirement.",
                                     {"protocol": protocol, "expected": expected, "actual": analysis["protocols"].get(protocol)}))
    mappings = rule.get("signal_nets", {})
    if not isinstance(mappings, dict) or not all(isinstance(pin, str) and isinstance(net, str) and net for pin, net in mappings.items()):
        raise ValueError("firmware signal_nets must map pin names to reviewed net names.")
    final_levels = _final_trace_levels(circuit)
    for pin, net in mappings.items():
        intended = analysis["pins"].get(pin, {}).get("digital_write")
        if intended is None:
            continue
        actual = final_levels.get(circuit.canonical_net(net))
        if actual is None:
            findings.append(_finding("FIRMWARE_TRACE_UNAVAILABLE", "warning", f"No final analyzer level was captured for firmware pin {pin}.", {"pin": pin, "net": net}))
        elif actual != (intended == "HIGH"):
            findings.append(_finding("FIRMWARE_TRACE_MISMATCH", "error", "Captured output level differs from literal firmware output intent.",
                                     {"pin": pin, "net": net, "firmware_level": intended, "trace_level": int(actual)}))
    return findings


def _final_trace_levels(circuit) -> dict[str, bool]:
    trace = circuit.measurements.get("digital_trace")
    if not isinstance(trace, list):
        return {}
    levels: dict[str, bool] = {}
    for event in trace:
        if not isinstance(event, dict) or not isinstance(event.get("levels"), dict):
            continue
        for net, value in event["levels"].items():
            if value in (True, 1):
                levels[circuit.canonical_net(net)] = True
            elif value in (False, 0):
                levels[circuit.canonical_net(net)] = False
    return levels


def _finding(code: str, severity: str, message: str, evidence: dict[str, Any]) -> dict[str, Any]:
    return {"code": code, "severity": severity, "message": message, "evidence": evidence}
