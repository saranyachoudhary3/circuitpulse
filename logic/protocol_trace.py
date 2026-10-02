"""Fail-closed I²C, SPI, and UART decoding from captured digital traces."""

from __future__ import annotations

from typing import Any

from logic.circuit_ir import CircuitIR, CircuitIRError


class ProtocolTraceError(ValueError):
    pass


class ProtocolTraceEvaluator:
    """Decode only explicitly named logic-analyzer channels.

    Trace samples are time ordered and represent signal updates.  No protocol
    channel, polarity, clock mode, or address is inferred from its appearance.
    An incomplete capture produces a warning/indeterminate finding instead of
    a successful bus claim.
    """

    def evaluate(self, circuit: CircuitIR, rule: dict[str, Any]) -> dict[str, Any]:
        kind = rule.get("kind")
        trace = self._trace(circuit)
        if kind == "i2c_trace":
            return self._i2c(circuit, trace, rule)
        if kind == "spi_trace":
            return self._spi(circuit, trace, rule)
        if kind == "uart_trace":
            return self._uart(circuit, trace, rule)
        raise ProtocolTraceError(f"Unsupported protocol-trace requirement {kind!r}.")

    def _trace(self, circuit: CircuitIR) -> list[dict[str, Any]]:
        raw = circuit.measurements.get("digital_trace")
        if not isinstance(raw, list) or not raw:
            raise ProtocolTraceError("measurements.digital_trace must contain captured logic-analyzer events.")
        result, last_time = [], -1.0
        for item in raw:
            if not isinstance(item, dict) or not isinstance(item.get("levels"), dict):
                raise ProtocolTraceError("Every digital trace event needs time_us and levels.")
            try:
                time_us = float(item["time_us"])
            except (KeyError, TypeError, ValueError) as error:
                raise ProtocolTraceError("Every digital trace event needs numeric time_us.") from error
            if time_us < last_time:
                raise ProtocolTraceError("Digital trace events must be time ordered.")
            levels = {}
            for net, value in item["levels"].items():
                parsed = self._level(value)
                if not isinstance(net, str) or not net or parsed is None:
                    raise ProtocolTraceError("Trace levels need non-empty net names and 0/1 values.")
                levels[circuit.canonical_net(net)] = parsed
            result.append({"time_us": time_us, "levels": levels})
            last_time = time_us
        return result

    def _i2c(self, circuit: CircuitIR, trace: list[dict[str, Any]], rule: dict[str, Any]) -> dict[str, Any]:
        try:
            sda, scl = circuit.canonical_net(rule["sda_net"]), circuit.canonical_net(rule["scl_net"])
        except (KeyError, CircuitIRError) as error:
            raise ProtocolTraceError("I2C trace rule needs sda_net and scl_net.") from error
        levels: dict[str, int] = {}
        active, starts, stops, bits, frames, transactions = False, 0, 0, [], [], []
        transaction_start = 0
        findings = []
        for event in trace:
            previous = dict(levels)
            levels.update(event["levels"])
            old_sda, new_sda = previous.get(sda), levels.get(sda)
            old_scl, new_scl = previous.get(scl), levels.get(scl)
            if old_sda == 1 and new_sda == 0 and new_scl == 1:
                if active and bits:
                    findings.append(self._finding("I2C_REPEATED_START_MID_BYTE", "error", "I2C repeated start occurred before a complete byte.", {"time_us": event["time_us"]}))
                if active and len(frames) > transaction_start:
                    transactions.append(frames[transaction_start:])
                transaction_start = len(frames)
                active, starts, bits = True, starts + 1, []
            if active and old_scl == 0 and new_scl == 1:
                if new_sda is None:
                    findings.append(self._finding("I2C_SAMPLE_UNAVAILABLE", "warning", "I2C clock edge has no SDA sample.", {"time_us": event["time_us"]}))
                else:
                    bits.append(new_sda)
                    if len(bits) == 9:
                        value = sum(bit << (7 - index) for index, bit in enumerate(bits[:8]))
                        frames.append({"byte": value, "ack": bits[8], "time_us": event["time_us"]})
                        bits = []
            if old_sda == 0 and new_sda == 1 and new_scl == 1:
                if not active:
                    findings.append(self._finding("I2C_STOP_WITHOUT_START", "error", "I2C stop condition occurred without a start.", {"time_us": event["time_us"]}))
                # A STOP condition necessarily raises SCL while SDA is low,
                # which looks like one candidate data sample before SDA rises.
                # Discard that protocol-control sample; any longer remainder
                # is a genuinely truncated byte.
                elif bits and not (len(bits) == 1 and bits[0] == 0):
                    findings.append(self._finding("I2C_INCOMPLETE_BYTE", "error", "I2C stop condition occurred before a complete byte.", {"bits": len(bits), "time_us": event["time_us"]}))
                if len(frames) > transaction_start:
                    transactions.append(frames[transaction_start:])
                active, stops = False, stops + 1
        if starts == 0:
            findings.append(self._finding("I2C_TRACE_NO_START", "warning", "No I2C start condition was captured.", {}))
        if active:
            findings.append(self._finding("I2C_TRACE_INCOMPLETE", "warning", "I2C capture ended before a stop condition.", {}))
        if rule.get("require_ack", True):
            nacks = [frame for frame in frames if frame["ack"] != 0]
            if nacks:
                findings.append(self._finding("I2C_NACK", "error", "A captured I2C byte was not acknowledged.", {"frames": nacks}))
        expected = self._addresses(rule.get("expected_addresses", []))
        # Only the first byte of each START-delimited transfer encodes the
        # address. Payload bytes can equal an address bit-pattern by chance.
        observed = sorted({transaction[0]["byte"] >> 1 for transaction in transactions if transaction})
        missing = sorted(expected - set(observed))
        if expected and missing:
            findings.append(self._finding("I2C_EXPECTED_ADDRESS_MISSING", "error", "Expected I2C address did not appear in the decoded capture.",
                                          {"missing_addresses": [hex(item) for item in missing], "observed_addresses": [hex(item) for item in observed]}))
        return {"status": self._status(findings), "findings": findings,
                "decoded": {"protocol": "i2c", "starts": starts, "stops": stops, "frames": frames,
                            "transactions": transactions, "addresses": [hex(item) for item in observed]}}

    def _spi(self, circuit: CircuitIR, trace: list[dict[str, Any]], rule: dict[str, Any]) -> dict[str, Any]:
        try:
            sck, mosi, miso, cs = (circuit.canonical_net(rule["sck_net"]), circuit.canonical_net(rule["mosi_net"]),
                                   circuit.canonical_net(rule["miso_net"]), circuit.canonical_net(rule["cs_net"]))
            cpol, cpha = int(rule.get("cpol", 0)), int(rule.get("cpha", 0))
            active_level = self._level(rule.get("cs_active", 0))
            if cpol not in {0, 1} or cpha not in {0, 1} or active_level is None:
                raise ValueError
        except (KeyError, TypeError, ValueError, CircuitIRError) as error:
            raise ProtocolTraceError("SPI trace needs sck_net, mosi_net, miso_net, cs_net, and CPOL/CPHA values of 0 or 1.") from error
        levels: dict[str, int] = {}
        mosi_bits, miso_bits, edge_times = [], [], []
        findings = []
        for event in trace:
            previous = dict(levels)
            levels.update(event["levels"])
            old_sck, new_sck = previous.get(sck), levels.get(sck)
            if levels.get(cs) != active_level or old_sck is None or new_sck is None or old_sck == new_sck:
                continue
            leading = new_sck != cpol
            if (cpha == 0 and not leading) or (cpha == 1 and leading):
                continue
            if levels.get(mosi) is None or levels.get(miso) is None:
                findings.append(self._finding("SPI_SAMPLE_UNAVAILABLE", "warning", "SPI sampling edge has no MOSI or MISO value.", {"time_us": event["time_us"]}))
                continue
            edge_times.append(event["time_us"])
            mosi_bits.append(levels[mosi])
            miso_bits.append(levels[miso])
        minimum_period = rule.get("min_clock_period_us")
        if minimum_period is not None:
            try:
                minimum_period = float(minimum_period)
                if minimum_period <= 0:
                    raise ValueError
                periods = [later - earlier for earlier, later in zip(edge_times, edge_times[1:])]
                too_fast = [period for period in periods if period < minimum_period]
                if too_fast:
                    findings.append(self._finding("SPI_CLOCK_TOO_FAST", "error", "Captured SPI sampling edges violate the reviewed minimum clock period.",
                                                  {"minimum_clock_period_us": minimum_period, "observed_periods_us": too_fast}))
            except (TypeError, ValueError):
                raise ProtocolTraceError("SPI min_clock_period_us must be a positive number.")
        if len(mosi_bits) % 8:
            findings.append(self._finding("SPI_INCOMPLETE_BYTE", "warning", "SPI capture ends with a partial byte.", {"bits": len(mosi_bits) % 8}))
        mosi_bytes, miso_bytes = self._bytes(mosi_bits), self._bytes(miso_bits)
        expected_mosi = self._byte_list(rule.get("expected_mosi_bytes"))
        if expected_mosi is not None and mosi_bytes != expected_mosi:
            findings.append(self._finding("SPI_MOSI_MISMATCH", "error", "Decoded SPI MOSI bytes differ from the reviewed expectation.",
                                          {"expected": expected_mosi, "actual": mosi_bytes}))
        if not edge_times:
            findings.append(self._finding("SPI_TRACE_NO_TRANSFER", "warning", "No SPI sampling edges were captured while chip select was active.", {}))
        return {"status": self._status(findings), "findings": findings,
                "decoded": {"protocol": "spi", "mosi_bytes": mosi_bytes, "miso_bytes": miso_bytes, "sample_edges": len(edge_times)}}

    def _uart(self, circuit: CircuitIR, trace: list[dict[str, Any]], rule: dict[str, Any]) -> dict[str, Any]:
        try:
            rx = circuit.canonical_net(rule["rx_net"])
            baud = float(rule["baud"])
            data_bits = int(rule.get("data_bits", 8))
            if baud <= 0 or data_bits not in {5, 6, 7, 8}:
                raise ValueError
        except (KeyError, TypeError, ValueError, CircuitIRError) as error:
            raise ProtocolTraceError("UART trace needs rx_net, positive baud, and data_bits from 5 to 8.") from error
        history, levels, falling = [], {}, []
        for event in trace:
            previous = levels.get(rx)
            levels.update(event["levels"])
            history.append((event["time_us"], dict(levels)))
            if previous == 1 and levels.get(rx) == 0:
                falling.append(event["time_us"])
        bit_time = 1_000_000 / baud
        decoded, findings, next_allowed = [], [], float("-inf")
        for start in falling:
            if start < next_allowed:
                continue
            if self._level_at(history, rx, start + bit_time / 2) != 0:
                continue
            values = [self._level_at(history, rx, start + bit_time * (1.5 + index)) for index in range(data_bits)]
            stop = self._level_at(history, rx, start + bit_time * (1.5 + data_bits))
            if any(value is None for value in values) or stop is None:
                findings.append(self._finding("UART_TRACE_INCOMPLETE", "warning", "UART capture ends before all data/stop samples are available.", {"start_time_us": start}))
                continue
            if stop != 1:
                findings.append(self._finding("UART_FRAMING_ERROR", "error", "UART stop bit was not high at the reviewed sample point.", {"start_time_us": start}))
            decoded.append(sum(value << index for index, value in enumerate(values)))
            next_allowed = start + bit_time * (data_bits + 1)
        expected = self._byte_list(rule.get("expected_bytes"))
        if expected is not None and decoded != expected:
            findings.append(self._finding("UART_PAYLOAD_MISMATCH", "error", "Decoded UART bytes differ from the reviewed expectation.", {"expected": expected, "actual": decoded}))
        if not decoded:
            findings.append(self._finding("UART_TRACE_NO_FRAME", "warning", "No complete UART frame was decoded from the capture.", {}))
        return {"status": self._status(findings), "findings": findings,
                "decoded": {"protocol": "uart", "baud": baud, "bytes": decoded}}

    @staticmethod
    def _level(value: Any) -> int | None:
        return 1 if value in (True, 1) else 0 if value in (False, 0) else None

    @staticmethod
    def _finding(code: str, severity: str, message: str, evidence: dict[str, Any]) -> dict[str, Any]:
        return {"code": code, "severity": severity, "message": message, "evidence": evidence}

    @staticmethod
    def _status(findings: list[dict[str, Any]]) -> str:
        return "FAIL" if any(item["severity"] in {"critical", "error"} for item in findings) else "INDETERMINATE" if findings else "PASS"

    @staticmethod
    def _bytes(bits: list[int]) -> list[int]:
        return [sum(bit << (7 - index) for index, bit in enumerate(bits[offset:offset + 8])) for offset in range(0, len(bits) - 7, 8)]

    @staticmethod
    def _addresses(raw: Any) -> set[int]:
        if raw is None:
            return set()
        if not isinstance(raw, list):
            raise ProtocolTraceError("I2C expected_addresses must be a list.")
        result = set()
        for item in raw:
            try:
                value = int(item, 0) if isinstance(item, str) else int(item)
            except (TypeError, ValueError) as error:
                raise ProtocolTraceError("I2C address values must be integers or 0x-prefixed strings.") from error
            if not 0 <= value <= 0x7F:
                raise ProtocolTraceError("I2C addresses must be seven-bit values.")
            result.add(value)
        return result

    @staticmethod
    def _byte_list(raw: Any) -> list[int] | None:
        if raw is None:
            return None
        if not isinstance(raw, list):
            raise ProtocolTraceError("Expected protocol bytes must be a list.")
        result = []
        for item in raw:
            try:
                value = int(item, 0) if isinstance(item, str) else int(item)
            except (TypeError, ValueError) as error:
                raise ProtocolTraceError("Expected protocol bytes must be integers or 0x-prefixed strings.") from error
            if not 0 <= value <= 0xFF:
                raise ProtocolTraceError("Expected protocol bytes must be between 0 and 255.")
            result.append(value)
        return result

    @staticmethod
    def _level_at(history: list[tuple[float, dict[str, int]]], net: str, time_us: float) -> int | None:
        state = None
        for timestamp, levels in history:
            if timestamp > time_us:
                break
            state = levels.get(net, state)
        return state
