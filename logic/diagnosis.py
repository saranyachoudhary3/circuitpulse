"""Causal prioritization for simultaneous deterministic circuit faults."""

from __future__ import annotations

from typing import Any


class FaultDiagnoser:
    """Identify known upstream faults without hiding independent evidence.

    The rule set is deliberately small and explicit. A downstream finding is
    retained for transparency, but labelled secondary if a deterministic power,
    topology, or protocol fault directly explains why it could occur.
    """

    DOWNSTREAM = {
        "DIRECT_POWER_SHORT": {"I2C_DEVICE_NO_ACK", "I2C_NACK", "I2C_EXPECTED_ADDRESS_MISSING", "SPI_TRACE_NO_TRANSFER", "UART_TRACE_NO_FRAME", "FIRMWARE_TRACE_MISMATCH"},
        "POWER_DOMAIN_OUT_OF_RANGE": {"I2C_DEVICE_NO_ACK", "I2C_NACK", "I2C_EXPECTED_ADDRESS_MISSING", "SPI_TRACE_NO_TRANSFER", "UART_TRACE_NO_FRAME", "FIRMWARE_TRACE_MISMATCH"},
        "REGULATOR_DROPOUT": {"I2C_DEVICE_NO_ACK", "I2C_NACK", "I2C_EXPECTED_ADDRESS_MISSING", "SPI_TRACE_NO_TRANSFER", "UART_TRACE_NO_FRAME", "FIRMWARE_TRACE_MISMATCH"},
        "CURRENT_BUDGET_EXCEEDED": {"I2C_DEVICE_NO_ACK", "I2C_NACK", "I2C_EXPECTED_ADDRESS_MISSING", "SPI_TRACE_NO_TRANSFER", "UART_TRACE_NO_FRAME", "FIRMWARE_TRACE_MISMATCH"},
        "I2C_LINES_SHORTED": {"I2C_DEVICE_NO_ACK", "I2C_NACK", "I2C_EXPECTED_ADDRESS_MISSING", "I2C_TRACE_NO_START"},
        "SPI_SIGNAL_SHORT": {"SPI_TRACE_NO_TRANSFER", "SPI_MOSI_MISMATCH"},
        "UART_LINES_SHORTED": {"UART_TRACE_NO_FRAME", "UART_FRAMING_ERROR", "UART_PAYLOAD_MISMATCH"},
        "LOGIC_LEVEL_OVERVOLTAGE": {"FIRMWARE_TRACE_MISMATCH", "UART_FRAMING_ERROR", "SPI_MOSI_MISMATCH"},
        "LED_CURRENT_LIMITER_MISSING": {"LED_NO_SOURCE_PATH"},
        "LED_REVERSED_POLARITY": {"LED_NO_SOURCE_PATH", "LED_NO_RETURN_PATH"},
        "REGULATOR_INPUT_OVERVOLTAGE": {"POWER_DOMAIN_OUT_OF_RANGE", "I2C_DEVICE_NO_ACK", "I2C_NACK"},
        "MOSFET_GATE_UNDERDRIVEN": {"FIRMWARE_TRACE_MISMATCH"},
        "GPIO_CURRENT_LIMIT_EXCEEDED": {"FIRMWARE_TRACE_MISMATCH", "I2C_DEVICE_NO_ACK"},
        "TRANSISTOR_CURRENT_LIMIT_EXCEEDED": {"FIRMWARE_TRACE_MISMATCH"},
        "COMPONENT_SELF_SHORT": {"DC_NODE_OUT_OF_RANGE", "RESISTOR_POWER_EXCEEDED"},
    }

    def diagnose(self, findings: list[dict[str, Any]]) -> dict[str, Any]:
        by_code = {item.get("code") for item in findings if isinstance(item, dict)}
        links = []
        secondary_codes = set()
        for cause, effects in self.DOWNSTREAM.items():
            if cause not in by_code:
                continue
            for effect in sorted(effects & by_code):
                links.append({"cause": cause, "effect": effect, "relationship": "can_explain"})
                secondary_codes.add(effect)
        primary, secondary = [], []
        for finding in findings:
            if finding.get("code") in secondary_codes:
                secondary.append({**finding, "diagnostic_role": "secondary_symptom"})
            else:
                primary.append({**finding, "diagnostic_role": "primary_or_independent"})
        return {"primary_findings": primary, "secondary_findings": secondary, "causal_links": links,
                "summary": "Resolve primary findings before reassessing linked secondary symptoms." if links else "No reviewed causal relationship links the current findings."}

    def diagnosis_summary(self, diagnosis_result: dict[str, Any]) -> str:
        """Return a plain-English summary of the top root causes for beginners."""
        primary = diagnosis_result.get("primary_findings", [])[:3]
        if not primary:
            return "No faults detected. Your circuit looks good!"
        lines = []
        for i, f in enumerate(primary, 1):
            msg = f.get("message", "Unknown issue")
            lines.append(f"{i}. {msg}")
        count = len(diagnosis_result.get("primary_findings", []))
        header = f"Found {count} issue(s) — here are the top priorities:"
        return header + "\n" + "\n".join(lines)
