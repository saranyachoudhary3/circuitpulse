"""Guarded local ngspice operating-point proof for reviewed circuit templates."""

from __future__ import annotations

import re
import shutil
import subprocess
from typing import Any


MAX_NETLIST_BYTES = 64 * 1024
_FORBIDDEN_DIRECTIVES = re.compile(r"(?im)^\s*(?:\.control|\.endc|\.shell|\.source|shell|system)\b")
_NUMBER = r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"


def run_operating_point(netlist: str, expected_node_ranges_v: dict[str, list[float]] | None = None,
                        timeout_seconds: float = 3.0) -> dict[str, Any]:
    """Run a bounded, non-interactive ``.op`` template and verify node ranges.

    This accepts a reviewed SPICE template only; it never executes a shell or a
    ngspice control block. Missing ngspice, timeouts, or absent requested node
    values are deliberately not treated as a passing electrical result.
    """
    template_error = _validate_template(netlist, expected_node_ranges_v, timeout_seconds)
    if template_error:
        return {"status": "FAIL", "reason": template_error, "evidence_mode": "simulation_template_invalid"}
    executable = shutil.which("ngspice")
    if executable is None:
        return {"status": "INDETERMINATE", "reason": "ngspice is not installed", "evidence_mode": "simulation_unavailable"}
    try:
        result = subprocess.run([executable, "-b"], input=netlist, text=True, capture_output=True,
                                timeout=timeout_seconds, check=False)
    except subprocess.TimeoutExpired:
        return {"status": "INDETERMINATE", "reason": "ngspice operating-point analysis timed out", "evidence_mode": "simulation_timeout"}
    output = (result.stdout or "") + "\n" + (result.stderr or "")
    if result.returncode or re.search(r"(?im)^\s*(?:fatal )?error\s*[:!]", output):
        return {"status": "FAIL", "reason": "ngspice rejected the circuit netlist", "output": output[-2000:], "evidence_mode": "simulation"}
    ranges = expected_node_ranges_v or {}
    voltages, missing = _extract_expected_nodes(output, ranges)
    if missing:
        return {"status": "INDETERMINATE", "reason": f"ngspice did not report required node voltages: {missing}",
                "output": output[-2000:], "evidence_mode": "simulation_incomplete"}
    out_of_range = []
    for node, bounds in ranges.items():
        minimum, maximum = float(bounds[0]), float(bounds[1])
        if not minimum <= voltages[node] <= maximum:
            out_of_range.append({"node": node, "voltage_v": voltages[node], "min_v": minimum, "max_v": maximum})
    if out_of_range:
        return {"status": "FAIL", "reason": "ngspice node voltage is outside the reviewed safe range.",
                "node_voltages_v": voltages, "out_of_range": out_of_range, "evidence_mode": "simulation"}
    return {"status": "PASS", "node_voltages_v": voltages, "output": output[-2000:], "evidence_mode": "simulation"}


def run_measured_analysis(netlist: str, analysis: str, expected_measurements: dict[str, list[float]],
                          timeout_seconds: float = 3.0) -> dict[str, Any]:
    """Run a reviewed ``.tran`` or ``.ac`` deck with bounded `.meas` gates."""
    directives = {"transient": ".tran", "ac": ".ac"}
    directive = directives.get(analysis)
    if directive is None:
        return {"status": "FAIL", "reason": "SPICE analysis must be transient or ac.", "evidence_mode": "simulation_template_invalid"}
    if not isinstance(expected_measurements, dict):
        return {"status": "FAIL", "reason": "Transient/AC SPICE analysis requires expected_measurements.", "evidence_mode": "simulation_template_invalid"}
    template_error = _validate_template(netlist, expected_measurements, timeout_seconds, directive, measurements=True)
    if template_error:
        return {"status": "FAIL", "reason": template_error, "evidence_mode": "simulation_template_invalid"}
    executable = shutil.which("ngspice")
    if executable is None:
        return {"status": "INDETERMINATE", "reason": "ngspice is not installed", "evidence_mode": "simulation_unavailable"}
    try:
        result = subprocess.run([executable, "-b"], input=netlist, text=True, capture_output=True,
                                timeout=timeout_seconds, check=False)
    except subprocess.TimeoutExpired:
        return {"status": "INDETERMINATE", "reason": f"ngspice {analysis} analysis timed out", "evidence_mode": "simulation_timeout"}
    output = (result.stdout or "") + "\n" + (result.stderr or "")
    if result.returncode or re.search(r"(?im)^\s*(?:fatal )?error\s*[:!]", output):
        return {"status": "FAIL", "reason": "ngspice rejected the circuit netlist", "output": output[-2000:], "evidence_mode": "simulation"}
    values, missing = _extract_measurements(output, expected_measurements)
    if missing:
        return {"status": "INDETERMINATE", "reason": f"ngspice did not report required .meas values: {missing}",
                "output": output[-2000:], "evidence_mode": "simulation_incomplete"}
    out_of_range = []
    for name, bounds in expected_measurements.items():
        minimum, maximum = float(bounds[0]), float(bounds[1])
        if not minimum <= values[name] <= maximum:
            out_of_range.append({"measurement": name, "value": values[name], "min": minimum, "max": maximum})
    if out_of_range:
        return {"status": "FAIL", "reason": "ngspice measurement is outside the reviewed safe range.", "measurements": values,
                "out_of_range": out_of_range, "evidence_mode": "simulation"}
    return {"status": "PASS", "measurements": values, "output": output[-2000:], "evidence_mode": "simulation"}


def _validate_template(netlist: Any, ranges: Any, timeout_seconds: float, directive: str = ".op", measurements: bool = False) -> str | None:
    if not isinstance(netlist, str) or not netlist.strip():
        return "SPICE operating-point rule requires a non-empty netlist."
    if len(netlist.encode("utf-8")) > MAX_NETLIST_BYTES or "\x00" in netlist:
        return "SPICE netlist is too large or contains an invalid NUL byte."
    if not re.search(rf"(?im)^\s*{re.escape(directive)}\b", netlist) or not re.search(r"(?im)^\s*\.end\s*$", netlist):
        return f"SPICE template must contain {directive} and .end directives."
    if _FORBIDDEN_DIRECTIVES.search(netlist):
        return "SPICE control, shell, and source directives are forbidden in CircuitPulse templates."
    if not isinstance(timeout_seconds, (int, float)) or not 0 < timeout_seconds <= 10:
        return "SPICE timeout must be between zero and ten seconds."
    if ranges is not None:
        if not isinstance(ranges, dict):
            return "Expected SPICE ranges must be an object."
        if measurements and not ranges:
            return "Transient/AC SPICE analysis requires at least one expected measurement range."
        for node, bounds in ranges.items():
            if not isinstance(node, str) or not node or not isinstance(bounds, list) or len(bounds) != 2:
                return "Every expected SPICE value needs [minimum, maximum]."
            if measurements and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", node):
                return "SPICE .meas names must be simple identifiers."
            try:
                if float(bounds[0]) > float(bounds[1]):
                    return f"Expected SPICE range for {node} is reversed."
            except (TypeError, ValueError):
                return f"Expected SPICE range for {node} must be numeric."
    return None


def _extract_expected_nodes(output: str, ranges: dict[str, list[float]]) -> tuple[dict[str, float], list[str]]:
    values: dict[str, float] = {}
    for node in ranges:
        escaped = re.escape(node)
        match = re.search(rf"(?im)\bv\(\s*{escaped}\s*\)\s*(?:=|\s)\s*{_NUMBER}\b", output)
        if match:
            values[node] = float(match.group(1))
    return values, [node for node in ranges if node not in values]


def _extract_measurements(output: str, ranges: dict[str, list[float]]) -> tuple[dict[str, float], list[str]]:
    values = {}
    for name in ranges:
        match = re.search(rf"(?im)^\s*{re.escape(name)}\s*=\s*{_NUMBER}\s*$", output)
        if match:
            values[name] = float(match.group(1))
    return values, [name for name in ranges if name not in values]
