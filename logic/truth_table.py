"""Exhaustive reviewed truth-table validation for combinational logic graphs."""

from __future__ import annotations

from typing import Any

from logic.circuit_ir import CircuitIR, CircuitIRError
from logic.digital_logic import DigitalLogicError, DigitalLogicEvaluator


class TruthTableError(ValueError):
    pass


class TruthTableVerifier:
    """Evaluate each explicit row; no desired boolean function is inferred."""

    MAX_ROWS = 256

    def verify(self, circuit: CircuitIR, rule: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            inputs = rule["input_nets"]
            output_net = circuit.canonical_net(rule["output_net"])
            rows = rule["rows"]
            if not isinstance(inputs, list) or not inputs or not all(isinstance(net, str) and net for net in inputs):
                raise TruthTableError("Truth-table input_nets must be a non-empty list of net names.")
            canonical_inputs = [circuit.canonical_net(net) for net in inputs]
            if len(set(canonical_inputs)) != len(canonical_inputs):
                raise TruthTableError("Truth-table input_nets must be electrically distinct.")
            if not isinstance(rows, list) or not rows or len(rows) > self.MAX_ROWS:
                raise TruthTableError(f"Truth table requires 1 to {self.MAX_ROWS} rows.")
            seen, findings = set(), []
            for index, row in enumerate(rows):
                if not isinstance(row, dict) or not isinstance(row.get("inputs"), dict):
                    raise TruthTableError("Every truth-table row needs inputs and output.")
                supplied = row["inputs"]
                if set(supplied) != set(inputs):
                    raise TruthTableError("Every truth-table row must specify exactly every input net.")
                values = {net: self._level(supplied[net]) for net in inputs}
                expected = self._level(row.get("output"))
                if expected is None or any(value is None for value in values.values()):
                    raise TruthTableError("Truth-table values must be 0/1/false/true.")
                signature = tuple(int(values[net]) for net in inputs)
                if signature in seen:
                    raise TruthTableError("Truth-table rows may not duplicate an input combination.")
                seen.add(signature)
                result = DigitalLogicEvaluator().evaluate(circuit, initial_levels=values)
                actual = result["levels"].get(output_net)
                if actual is None:
                    findings.append(self._finding("TRUTH_TABLE_OUTPUT_UNRESOLVED", "warning", "Declared logic output cannot be resolved for a truth-table row.",
                                                  {"row": index, "inputs": values, "output_net": output_net}))
                elif actual != int(expected):
                    findings.append(self._finding("TRUTH_TABLE_MISMATCH", "error", "Combinational output does not match its reviewed truth-table row.",
                                                  {"row": index, "inputs": values, "output_net": output_net, "expected": int(expected), "actual": actual}))
                findings.extend(item for item in result["findings"] if item["code"] in {"DIGITAL_LOGIC_CONTENTION", "DIGITAL_LOGIC_UNRESOLVED"})
            required_rows = 1 << len(inputs)
            if rule.get("require_complete", True) and len(seen) != required_rows:
                findings.append(self._finding("TRUTH_TABLE_INCOMPLETE", "warning", "Truth table does not cover every input combination.",
                                              {"provided_rows": len(seen), "required_rows": required_rows}))
            return findings
        except (KeyError, TypeError, ValueError, CircuitIRError, DigitalLogicError, TruthTableError) as error:
            return [self._finding("TRUTH_TABLE_REQUIREMENT_INVALID", "error", str(error), {"requirement": rule})]

    @staticmethod
    def _level(value: Any) -> bool | None:
        return True if value in (True, 1) else False if value in (False, 0) else None

    @staticmethod
    def _finding(code: str, severity: str, message: str, evidence: dict[str, Any]) -> dict[str, Any]:
        return {"code": code, "severity": severity, "message": message, "evidence": evidence}
