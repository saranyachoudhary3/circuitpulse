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
