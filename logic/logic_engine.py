"""Deterministic typed-circuit rules and root-cause ranking."""

from __future__ import annotations

from typing import Any

from logic.circuit_ir import CircuitIR, CircuitIRError, CircuitComponent
from logic.netlist import NetlistError, NetlistVerifier
from logic.dc_solver import DCSolverError, LinearDCSolver
from logic.digital_logic import DigitalLogicError, DigitalLogicEvaluator
from logic.repair_planner import RepairPlanner
from logic.temporal_analysis import TemporalAnalyzer
from logic.measurement_checks import MeasurementChecks
from logic.simulation import run_measured_analysis, run_operating_point
from logic.sequential_logic import SequentialLogicError, SequentialLogicEvaluator
from logic.protocol_trace import ProtocolTraceError, ProtocolTraceEvaluator
from logic.firmware import verify_firmware_contract
from logic.diagnosis import FaultDiagnoser
from logic.tolerance_analysis import ToleranceAnalyzer
from logic.power_sequence import PowerSequenceAnalyzer
from logic.adc_analysis import ADCAnalyzer
from logic.clock_analysis import ClockAnalyzer
from logic.thermal_analysis import ThermalAnalyzer
from logic.truth_table import TruthTableVerifier
from logic.temporal_assertions import TemporalAssertionVerifier
from logic.state_machine import StateMachineVerifier


class CircuitLogicEngine:
    """Analyze only explicitly declared circuit facts and measurements.

    The engine is extensible through ``requirements``. A requirement is a
    reviewed, deterministic rule pack entry; unsupported requirements return
    an explicit warning rather than an invented electrical conclusion.
    """

    def analyze(self, payload: dict[str, Any]) -> dict[str, Any]:
        circuit = CircuitIR(payload)
        findings: list[dict[str, Any]] = []
        try:
            base = NetlistVerifier().verify(payload)
            findings.extend(base["findings"])
        except NetlistError as error:
            raise CircuitIRError(str(error)) from error
        for component in circuit.components.values():
            findings.extend(self._passive_limits(component))
        for requirement in circuit.requirements:
            findings.extend(self._requirement(circuit, requirement))
        status = "FAIL" if any(item["severity"] in {"critical", "error"} for item in findings) else (
            "INDETERMINATE" if any(item["severity"] == "warning" for item in findings) else "PASS"
        )
        ranked = sorted(findings, key=lambda item: ({"critical": 0, "error": 1, "warning": 2, "info": 3}.get(item["severity"], 4), item["code"]))
        diagnosis = FaultDiagnoser().diagnose(ranked)
        return {"status": status, "findings": ranked, "diagnosis": diagnosis, "root_causes": self._root_causes(diagnosis["primary_findings"]),
                "checked_components": len(circuit.components), "evidence_mode": "typed_circuit_ir"}

    def _passive_limits(self, component: CircuitComponent) -> list[dict[str, Any]]:
        raw, findings = component.raw, []
        if component.type == "resistor":
            value = raw.get("value_ohms")
            if not isinstance(value, (int, float)) or value <= 0:
                findings.append(self._finding("RESISTOR_VALUE_INVALID", "error", "Resistor requires a positive value_ohms.", component.id))
                return findings
            voltage = raw.get("voltage_across_v")
            rating = raw.get("power_rating_w")
            if voltage is not None and rating is not None:
                try:
                    power = float(voltage) ** 2 / float(value)
                    if power > float(rating):
                        findings.append(self._finding("RESISTOR_POWER_EXCEEDED", "critical", f"Calculated resistor dissipation {power:.3f} W exceeds its declared rating.", component.id, {"calculated_power_w": round(power, 4), "rating_w": rating}))
                except (TypeError, ValueError, ZeroDivisionError):
                    findings.append(self._finding("RESISTOR_RATING_INVALID", "error", "Resistor voltage/rating values must be numeric.", component.id))
        if component.type in {"capacitor", "diode", "led"}:
            voltage, rating = raw.get("voltage_across_v"), raw.get("voltage_rating_v")
            if voltage is not None and rating is not None:
                try:
                    if abs(float(voltage)) > float(rating):
                        findings.append(self._finding("COMPONENT_VOLTAGE_RATING_EXCEEDED", "critical", "Declared voltage exceeds component voltage rating.", component.id, {"voltage_v": voltage, "rating_v": rating}))
                except (TypeError, ValueError):
                    findings.append(self._finding("COMPONENT_RATING_INVALID", "error", "Component voltage/rating values must be numeric.", component.id))
        return findings

    def _requirement(self, circuit: CircuitIR, requirement: dict[str, Any]) -> list[dict[str, Any]]:
        kind = requirement.get("kind")
        if kind == "voltage_divider":
            return self._voltage_divider(circuit, requirement)
        if kind == "voltage_divider_tolerance":
            return ToleranceAnalyzer().voltage_divider(circuit, requirement)
        if kind == "i2c":
            return self._i2c(circuit, requirement)
        if kind == "spi":
            return self._spi(circuit, requirement)
        if kind == "gpio_output":
            return self._gpio_output(requirement)
        if kind == "inductive_load":
            return self._inductive_load(circuit, requirement)
        if kind == "dc_operating_point":
            return self._dc_operating_point(circuit, requirement)
        if kind == "digital_logic":
            return self._digital_logic(circuit, requirement)
        if kind == "digital_truth_table":
            return TruthTableVerifier().verify(circuit, requirement)
        if kind == "sequential_logic":
            return self._sequential_logic(circuit, requirement)
        if kind == "temporal_assertion":
            return TemporalAssertionVerifier().verify(circuit, requirement)
        if kind == "state_machine_trace":
            return StateMachineVerifier().verify(circuit, requirement)
        if kind == "power_domain":
            return self._power_domain(requirement)
        if kind == "uart":
            return self._uart(circuit, requirement)
        if kind == "rc_timing":
            return TemporalAnalyzer().rc_timing(circuit, requirement)
        if kind == "rc_tolerance":
            return ToleranceAnalyzer().rc_timing(circuit, requirement)
        if kind == "measurement_range":
            return MeasurementChecks().range_check(circuit, requirement)
        if kind == "adc":
            return ADCAnalyzer().evaluate(circuit, requirement)
        if kind == "clock_timing":
            return ClockAnalyzer().evaluate(circuit, requirement)
        if kind == "thermal":
            return ThermalAnalyzer().evaluate(requirement)
        if kind == "pwm":
            return MeasurementChecks().pwm(circuit, requirement)
        if kind == "i2c_ack":
            return MeasurementChecks().i2c_ack(circuit, requirement)
        if kind in {"i2c_trace", "spi_trace", "uart_trace"}:
            return self._protocol_trace(circuit, requirement)
        if kind == "firmware_contract":
            return self._firmware_contract(circuit, requirement)
        if kind == "logic_level_interface":
            return self._logic_level_interface(requirement)
        if kind == "regulator":
            return self._regulator(requirement)
        if kind == "transistor_driver":
            return self._transistor_driver(requirement)
        if kind == "spice_operating_point":
            return self._spice_operating_point(requirement)
        if kind in {"spice_transient", "spice_ac"}:
            return self._spice_measured_analysis(requirement, "transient" if kind == "spice_transient" else "ac")
        if kind == "current_budget":
            return self._current_budget(requirement)
        if kind == "power_sequence":
            return PowerSequenceAnalyzer().evaluate(circuit, requirement)
        if kind == "op_amp_operating_point":
            return self._op_amp_operating_point(requirement)
        return [{"code": "UNSUPPORTED_REQUIREMENT", "severity": "warning", "message": f"No reviewed rule pack is installed for requirement kind {kind!r}.", "evidence": {"requirement": requirement}}]

    def _voltage_divider(self, circuit: CircuitIR, rule: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            upper, lower = circuit.component(rule["upper_resistor"]), circuit.component(rule["lower_resistor"])
            if upper.type != "resistor" or lower.type != "resistor":
                raise CircuitIRError("Voltage-divider legs must be resistors.")
            r1, r2 = float(upper.raw["value_ohms"]), float(lower.raw["value_ohms"])
            input_v = float(rule["input_voltage_v"])
            
            load_r = rule.get("load_resistance_ohms")
            if load_r is not None:
                r_parallel = (r2 * float(load_r)) / (r2 + float(load_r))
                output_v = input_v * r_parallel / (r1 + r_parallel)
                unloaded_v = input_v * r2 / (r1 + r2)
            else:
                output_v = input_v * r2 / (r1 + r2)
                unloaded_v = output_v
                
            output_net = circuit.canonical_net(rule["output_net"])
            if output_net not in {circuit.canonical_net(net) for net in upper.pins.values()} or output_net not in {circuit.canonical_net(net) for net in lower.pins.values()}:
                return [self._finding("DIVIDER_TOPOLOGY_INVALID", "error", "Both divider resistors must meet at output_net.", None)]
            minimum, maximum = float(rule.get("output_min_v", float("-inf"))), float(rule.get("output_max_v", float("inf")))
            
            findings = []
            if load_r is not None and (minimum <= unloaded_v <= maximum) and not (minimum <= output_v <= maximum):
                findings.append(self._finding("VOLTAGE_DIVIDER_LOADED_SAG", "warning", 
                    f"Loaded divider output {output_v:.3f} V sags outside the safe range (unloaded was {unloaded_v:.3f} V).", None, 
                    {"unloaded_v": round(unloaded_v, 4), "loaded_v": round(output_v, 4), "min_v": minimum, "max_v": maximum}))
                
            if not minimum <= output_v <= maximum:
                findings.append(self._finding("DIVIDER_OUTPUT_OUT_OF_RANGE", "critical", f"Calculated divider output {output_v:.3f} V is outside the declared safe range.", None, {"output_v": round(output_v, 4), "min_v": minimum, "max_v": maximum}))
            return findings
        except (KeyError, TypeError, ValueError, ZeroDivisionError, CircuitIRError) as error:
            return [self._finding("DIVIDER_REQUIREMENT_INVALID", "error", str(error), None)]

    def _i2c(self, circuit: CircuitIR, rule: dict[str, Any]) -> list[dict[str, Any]]:
        findings = []
        try:
            sda, scl, supply = (circuit.canonical_net(rule["sda_net"]), circuit.canonical_net(rule["scl_net"]), circuit.canonical_net(rule["supply_net"]))
            if circuit.same_net(sda, scl):
                findings.append(self._finding("I2C_LINES_SHORTED", "critical", "I2C SDA and SCL resolve to the same electrical net.", None))
            pullups = rule.get("pullup_resistors", [])
            if len(pullups) < 2:
                findings.append(self._finding("I2C_PULLUPS_MISSING", "error", "I2C requires declared pull-up resistors for SDA and SCL.", None))
            for identifier in pullups:
                resistor = circuit.component(identifier)
                resistor_nets = {circuit.canonical_net(net) for net in resistor.pins.values()}
                if resistor.type != "resistor" or supply not in resistor_nets or not ({sda, scl} & resistor_nets):
                    findings.append(self._finding("I2C_PULLUP_TOPOLOGY_INVALID", "error", "Each I2C pull-up must join supply to SDA or SCL.", identifier))
        except (KeyError, CircuitIRError) as error:
            findings.append(self._finding("I2C_REQUIREMENT_INVALID", "error", str(error), None))
        return findings

    def _spi(self, circuit: CircuitIR, rule: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            signals = rule["signals"]
            required = {"mosi", "miso", "sck", "cs"}
            if not isinstance(signals, dict) or set(signals) != required:
                raise CircuitIRError("SPI requirement needs exactly mosi, miso, sck, and cs signal nets.")
            canonical = [circuit.canonical_net(signals[name]) for name in sorted(required)]
            if len(set(canonical)) != len(canonical):
                return [self._finding("SPI_SIGNAL_SHORT", "critical", "SPI signal nets must be electrically distinct.", None)]
            return []
        except (KeyError, CircuitIRError) as error:
            return [self._finding("SPI_REQUIREMENT_INVALID", "error", str(error), None)]

    def _gpio_output(self, rule: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            current, maximum = float(rule["load_current_ma"]), float(rule["max_current_ma"])
            if current > maximum:
                return [self._finding("GPIO_CURRENT_LIMIT_EXCEEDED", "critical", "Declared GPIO load current exceeds the reviewed pin limit.", rule.get("component_id"), {"load_current_ma": current, "max_current_ma": maximum})]
            return []
        except (KeyError, TypeError, ValueError):
            return [self._finding("GPIO_REQUIREMENT_INVALID", "error", "GPIO rule needs numeric load_current_ma and max_current_ma.", rule.get("component_id"))]

    def _inductive_load(self, circuit: CircuitIR, rule: dict[str, Any]) -> list[dict[str, Any]]:
        component_id = rule.get("component_id")
        try:
            inductor = circuit.component(component_id) if component_id else None
        except CircuitIRError:
            inductor = None

        if inductor and inductor.type in {"motor", "dc_motor", "relay", "solenoid"}:
            pos_pin = inductor.pins.get("positive", inductor.pins.get("+", inductor.pins.get("1")))
            neg_pin = inductor.pins.get("negative", inductor.pins.get("-", inductor.pins.get("2")))
            
            if pos_pin and neg_pin:
                try:
                    pos_net = circuit.canonical_net(pos_pin)
                    neg_net = circuit.canonical_net(neg_pin)
                except CircuitIRError:
                    return []
                
                diodes = [c for c in circuit.components.values() if c.type == "diode"]
                for diode in diodes:
                    anode_pin = diode.pins.get("anode", diode.pins.get("+"))
                    cathode_pin = diode.pins.get("cathode", diode.pins.get("-"))
                    if not anode_pin or not cathode_pin:
                        continue
                    anode = circuit.canonical_net(anode_pin)
                    cathode = circuit.canonical_net(cathode_pin)
                    
                    # Check for correct antiparallel orientation
                    if cathode == pos_net and anode == neg_net:
                        return [] # PASS
                    if anode == pos_net and cathode == neg_net:
                        return [self._finding("FLYBACK_DIODE_REVERSED", "error", "Flyback diode is installed in reverse.", component_id)]
                
                # If no diode found in correct/reversed orientation
                return [self._finding("INDUCTIVE_LOAD_NO_FLYBACK", "warning", "Declared inductive load lacks flyback protection.", component_id)]
            
        # Fallback if no inductor found or missing component_id or pins
        if not rule.get("flyback_protection"):
            return [self._finding("FLYBACK_PROTECTION_MISSING", "critical", "Declared inductive load lacks flyback protection.", component_id)]
        return []

    def _dc_operating_point(self, circuit: CircuitIR, rule: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            result = LinearDCSolver().solve(circuit, rule["ground_net"])
        except (KeyError, DCSolverError, CircuitIRError) as error:
            return [self._finding("DC_ANALYSIS_INVALID", "error", str(error), None)]
        if result["status"] != "PASS":
            return [self._finding("DC_ANALYSIS_INDETERMINATE", "warning", result["reason"], None, result)]
        findings = []
        ranges = rule.get("expected_node_ranges", {})
        if not isinstance(ranges, dict):
            return [self._finding("DC_EXPECTATION_INVALID", "error", "expected_node_ranges must be an object.", None)]
        for net, bounds in ranges.items():
            try:
                minimum, maximum = float(bounds[0]), float(bounds[1])
                voltage = result["node_voltages_v"][circuit.canonical_net(net)]
            except (KeyError, TypeError, ValueError, IndexError, CircuitIRError) as error:
                findings.append(self._finding("DC_EXPECTATION_INVALID", "error", f"Invalid expected range for node {net}: {error}", None))
                continue
            if not minimum <= voltage <= maximum:
                findings.append(self._finding("DC_NODE_OUT_OF_RANGE", "critical", f"Calculated DC node {net} is outside its declared safe range.", None,
                                              {"net": net, "voltage_v": voltage, "min_v": minimum, "max_v": maximum}))
        return findings

    def _digital_logic(self, circuit: CircuitIR, rule: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            result = DigitalLogicEvaluator().evaluate(circuit, rule.get("expected_levels"))
        except DigitalLogicError as error:
            return [self._finding("DIGITAL_LOGIC_REQUIREMENT_INVALID", "error", str(error), None)]
        return result["findings"]

    def _sequential_logic(self, circuit: CircuitIR, rule: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            return SequentialLogicEvaluator().evaluate(circuit, rule.get("expected_final_levels"))["findings"]
        except SequentialLogicError as error:
            return [self._finding("SEQUENTIAL_LOGIC_REQUIREMENT_INVALID", "error", str(error), None)]

    def _protocol_trace(self, circuit: CircuitIR, rule: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            return ProtocolTraceEvaluator().evaluate(circuit, rule)["findings"]
        except ProtocolTraceError as error:
            return [self._finding("PROTOCOL_TRACE_REQUIREMENT_INVALID", "error", str(error), None)]

    def _firmware_contract(self, circuit: CircuitIR, rule: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            source = rule["source"]
            return verify_firmware_contract(source, rule, circuit)
        except (KeyError, TypeError, ValueError, CircuitIRError) as error:
            return [self._finding("FIRMWARE_CONTRACT_INVALID", "error", str(error), None)]

    def _power_domain(self, rule: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            voltage = float(rule["supply_voltage_v"])
            minimum, maximum = float(rule["min_voltage_v"]), float(rule["max_voltage_v"])
            if not minimum <= voltage <= maximum:
                return [self._finding("POWER_DOMAIN_OUT_OF_RANGE", "critical", "Declared supply voltage is outside the component's reviewed operating range.", rule.get("component_id"),
                                      {"supply_voltage_v": voltage, "min_voltage_v": minimum, "max_voltage_v": maximum})]
            return []
        except (KeyError, TypeError, ValueError):
            return [self._finding("POWER_DOMAIN_REQUIREMENT_INVALID", "error", "Power-domain rule needs numeric supply_voltage_v, min_voltage_v, and max_voltage_v.", rule.get("component_id"))]

    def _uart(self, circuit: CircuitIR, rule: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            tx, rx = circuit.canonical_net(rule["tx_net"]), circuit.canonical_net(rule["rx_net"])
            if tx == rx:
                return [self._finding("UART_LINES_SHORTED", "critical", "UART TX and RX resolve to the same electrical net.", None)]
            if rule.get("require_common_ground") and not isinstance(rule.get("ground_net"), str):
                return [self._finding("UART_GROUND_UNDECLARED", "error", "UART rule requires an explicit ground_net when common ground is required.", None)]
            return []
        except (KeyError, CircuitIRError) as error:
            return [self._finding("UART_REQUIREMENT_INVALID", "error", str(error), None)]

    def _logic_level_interface(self, rule: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            source_high = float(rule["source_high_v"])
            destination_max = float(rule["destination_max_v"])
            destination_min_high = float(rule.get("destination_min_high_v", 0))
            if source_high > destination_max:
                return [self._finding("LOGIC_LEVEL_OVERVOLTAGE", "critical", "Source logic-high voltage exceeds destination input maximum.", rule.get("component_id"),
                                      {"source_high_v": source_high, "destination_max_v": destination_max})]
            if source_high < destination_min_high:
                return [self._finding("LOGIC_LEVEL_UNDERVOLTAGE", "error", "Source logic-high voltage may not meet destination HIGH threshold.", rule.get("component_id"),
                                      {"source_high_v": source_high, "destination_min_high_v": destination_min_high})]
            return []
        except (KeyError, TypeError, ValueError):
            return [self._finding("LOGIC_LEVEL_REQUIREMENT_INVALID", "error", "Logic-level rule needs numeric source/destination voltage limits.", rule.get("component_id"))]

    def _regulator(self, rule: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            input_v, output_v, dropout_v = float(rule["input_voltage_v"]), float(rule["output_voltage_v"]), float(rule["dropout_v"])
            maximum_input = float(rule["max_input_voltage_v"])
            if input_v > maximum_input:
                return [self._finding("REGULATOR_INPUT_OVERVOLTAGE", "critical", "Regulator input exceeds its declared maximum.", rule.get("component_id"), {"input_voltage_v": input_v, "max_input_voltage_v": maximum_input})]
            if input_v < output_v + dropout_v:
                return [self._finding("REGULATOR_DROPOUT", "error", "Regulator input lacks required output-plus-dropout headroom.", rule.get("component_id"), {"input_voltage_v": input_v, "required_minimum_v": output_v + dropout_v})]
            return []
        except (KeyError, TypeError, ValueError):
            return [self._finding("REGULATOR_REQUIREMENT_INVALID", "error", "Regulator rule needs numeric input/output/dropout/max-input values.", rule.get("component_id"))]

    def _transistor_driver(self, rule: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            kind = rule["device"].lower()
            load_current, rated_current = float(rule["load_current_ma"]), float(rule["rated_current_ma"])
            if load_current > rated_current:
                return [self._finding("TRANSISTOR_CURRENT_LIMIT_EXCEEDED", "critical", "Declared driver load exceeds transistor/driver current rating.", rule.get("component_id"), {"load_current_ma": load_current, "rated_current_ma": rated_current})]
            if kind == "mosfet":
                drive, required = float(rule["gate_drive_v"]), float(rule["required_gate_drive_v"])
                if drive < required:
                    return [self._finding("MOSFET_GATE_UNDERDRIVEN", "error", "Declared MOSFET gate drive is below its reviewed drive requirement.", rule.get("component_id"), {"gate_drive_v": drive, "required_gate_drive_v": required})]
            elif kind == "bjt":
                base, required = float(rule["base_current_ma"]), float(rule["required_base_current_ma"])
                if base < required:
                    return [self._finding("BJT_BASE_UNDERDRIVEN", "error", "Declared BJT base current is below the reviewed saturation requirement.", rule.get("component_id"), {"base_current_ma": base, "required_base_current_ma": required})]
            else:
                return [self._finding("TRANSISTOR_DRIVER_INVALID", "error", "Driver device must be mosfet or bjt.", rule.get("component_id"))]
            return []
        except (KeyError, TypeError, ValueError):
            return [self._finding("TRANSISTOR_DRIVER_INVALID", "error", "Driver rule is missing numeric load/rating/drive values.", rule.get("component_id"))]

    def _spice_operating_point(self, rule: dict[str, Any]) -> list[dict[str, Any]]:
        result = run_operating_point(rule.get("netlist"), rule.get("expected_node_ranges_v"), rule.get("timeout_seconds", 3.0))
        if result["status"] == "PASS":
            return []
        if result["status"] == "INDETERMINATE":
            return [self._finding("SPICE_OPERATING_POINT_INDETERMINATE", "warning", result["reason"], None, result)]
        code = "SPICE_NODE_OUT_OF_RANGE" if result.get("out_of_range") else "SPICE_OPERATING_POINT_FAILED"
        return [self._finding(code, "critical", result["reason"], None, result)]

    def _spice_measured_analysis(self, rule: dict[str, Any], analysis: str) -> list[dict[str, Any]]:
        result = run_measured_analysis(rule.get("netlist"), analysis, rule.get("expected_measurements"), rule.get("timeout_seconds", 3.0))
        prefix = "SPICE_TRANSIENT" if analysis == "transient" else "SPICE_AC"
        if result["status"] == "PASS":
            return []
        if result["status"] == "INDETERMINATE":
            return [self._finding(f"{prefix}_INDETERMINATE", "warning", result["reason"], None, result)]
        code = f"{prefix}_MEASUREMENT_OUT_OF_RANGE" if result.get("out_of_range") else f"{prefix}_FAILED"
        return [self._finding(code, "critical", result["reason"], None, result)]

    def _current_budget(self, rule: dict[str, Any]) -> list[dict[str, Any]]:
        """Check reviewed continuous current headroom with an explicit derating."""
        try:
            available = float(rule["available_current_ma"])
            derating = float(rule.get("derating_fraction", 0.8))
            loads = rule["loads"]
            if available <= 0 or not 0 < derating <= 1 or not isinstance(loads, list) or not loads:
                raise ValueError
            normalized = []
            for load in loads:
                if not isinstance(load, dict) or not isinstance(load.get("component_id"), str):
                    raise ValueError
                current = float(load["current_ma"])
                if current < 0:
                    raise ValueError
                normalized.append({"component_id": load["component_id"], "current_ma": current})
            total = sum(item["current_ma"] for item in normalized)
            limit = available * derating
            if total > limit:
                return [self._finding("CURRENT_BUDGET_EXCEEDED", "critical", "Declared continuous load current exceeds the reviewed derated source budget.", rule.get("source_id"),
                                      {"total_load_ma": total, "available_current_ma": available, "derating_fraction": derating,
                                       "derated_limit_ma": limit, "loads": normalized})]
            return []
        except (KeyError, TypeError, ValueError):
            return [self._finding("CURRENT_BUDGET_REQUIREMENT_INVALID", "error", "Current-budget rule needs a positive source limit, 0<derating<=1, and non-negative named loads.", rule.get("source_id"))]

    def _op_amp_operating_point(self, rule: dict[str, Any]) -> list[dict[str, Any]]:
        """Guard a declared op-amp operating point against reviewed envelope limits."""
        try:
            input_v = [float(rule["noninverting_voltage_v"]), float(rule["inverting_voltage_v"])]
            common_mode_min, common_mode_max = float(rule["common_mode_min_v"]), float(rule["common_mode_max_v"])
            output_v = float(rule["expected_output_v"])
            output_min, output_max = float(rule["output_min_v"]), float(rule["output_max_v"])
            if common_mode_min > common_mode_max or output_min > output_max:
                raise ValueError
            if any(not common_mode_min <= value <= common_mode_max for value in input_v):
                return [self._finding("OP_AMP_COMMON_MODE_OUT_OF_RANGE", "critical", "Declared op-amp input voltage is outside the reviewed common-mode range.", rule.get("component_id"),
                                      {"inputs_v": input_v, "common_mode_min_v": common_mode_min, "common_mode_max_v": common_mode_max})]
            if not output_min <= output_v <= output_max:
                return [self._finding("OP_AMP_OUTPUT_OUT_OF_RANGE", "critical", "Declared op-amp output is outside its reviewed output-swing range.", rule.get("component_id"),
                                      {"expected_output_v": output_v, "output_min_v": output_min, "output_max_v": output_max})]
            return []
        except (KeyError, TypeError, ValueError):
            return [self._finding("OP_AMP_REQUIREMENT_INVALID", "error", "Op-amp rule needs numeric input, common-mode, expected-output, and output-swing values.", rule.get("component_id"))]

    @staticmethod
    def _finding(code: str, severity: str, message: str, component_id: str | None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        evidence = {"component_id": component_id} if component_id else {}
        if extra:
            evidence.update(extra)
        return {"code": code, "severity": severity, "message": message, "evidence": evidence}

    @staticmethod
    def _root_causes(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        actions = {
            "DIVIDER_OUTPUT_OUT_OF_RANGE": "Change the upper/lower resistor ratio so the calculated output is inside the declared input range.",
            "DIVIDER_TOPOLOGY_INVALID": "Reconnect both divider resistors to the declared midpoint net before connecting the analog input.",
            "DIVIDER_TOLERANCE_OUT_OF_RANGE": "Choose tighter resistor/source tolerances or a safer divider ratio so all worst-case outputs remain in range.",
            "I2C_LINES_SHORTED": "Separate SDA and SCL; they must not share a conductor.",
            "I2C_PULLUPS_MISSING": "Add one reviewed pull-up resistor from SDA to supply and one from SCL to supply.",
            "I2C_PULLUP_TOPOLOGY_INVALID": "Move the listed pull-up so it joins the supply rail to exactly SDA or SCL.",
            "SPI_SIGNAL_SHORT": "Separate MOSI, MISO, SCK, and CS into distinct conductors.",
            "GPIO_CURRENT_LIMIT_EXCEEDED": "Move the load to a transistor or driver stage, or reduce the declared GPIO load current below its limit.",
            "FLYBACK_PROTECTION_MISSING": "Install an appropriately rated flyback diode across the inductive load before powering it.",
            "RESISTOR_POWER_EXCEEDED": "Use a higher-wattage resistor or reduce the voltage/current across it.",
            "COMPONENT_VOLTAGE_RATING_EXCEEDED": "Use a component with a higher voltage rating or reduce the applied voltage.",
            "DC_NODE_OUT_OF_RANGE": "Correct the supply or resistor network until the measured/calculated node voltage is inside the stated range.",
            "DIGITAL_EXPECTATION_MISMATCH": "Trace the named logic inputs and gate wiring, then correct the gate input or output connection.",
            "DIGITAL_LOGIC_CONTENTION": "Remove the conflicting output driver or isolate the outputs with appropriate logic circuitry.",
            "TRUTH_TABLE_MISMATCH": "Trace the named gate inputs and output wiring; the circuit fails a reviewed boolean-function row.",
            "TRUTH_TABLE_INCOMPLETE": "Add every input combination to the reviewed truth table before claiming exhaustive logic coverage.",
            "TEMPORAL_RESPONSE_TIMEOUT": "Check the trigger path, firmware timing, sensor/module power, and response signal routing.",
            "TEMPORAL_RESPONSE_OUT_OF_RANGE": "Correct firmware timing, sensor configuration, or circuit delays to meet the reviewed response window.",
            "STATE_MACHINE_TRANSITION_MISMATCH": "Trace the clock, reset, state bits, and input logic; the captured next state violates the reviewed state machine.",
            "STATE_MACHINE_TRANSITION_UNDECLARED": "Add a reviewed state-table row or correct unexpected state/input wiring before accepting the control logic.",
            "SEQUENTIAL_EXPECTATION_MISMATCH": "Trace the clock edge, reset state, and flip-flop inputs; then correct the sequential wiring or timing.",
            "SEQUENTIAL_INPUT_UNRESOLVED": "Capture the missing clock/input state with a logic analyzer before accepting a sequential-logic verdict.",
            "SEQUENTIAL_SETUP_TIME_VIOLATION": "Increase input setup margin or correct the clock/data timing before trusting the sequential state.",
            "SEQUENTIAL_HOLD_TIME_VIOLATION": "Keep the sequential input stable for the reviewed hold interval after the clock edge.",
            "I2C_NACK": "Check sensor power, common ground, pull-ups, bus routing, and the configured I2C address.",
            "I2C_EXPECTED_ADDRESS_MISSING": "Check the sensor address, SDA/SCL wiring, and the logic-analyzer channel mapping.",
            "SPI_CLOCK_TOO_FAST": "Reduce SPI clock speed or use components and wiring rated for the reviewed timing limit.",
            "SPI_MOSI_MISMATCH": "Check SPI mode, chip select, byte order, firmware payload, and MOSI wiring.",
            "UART_FRAMING_ERROR": "Check UART baud rate, common ground, polarity, and RX signal integrity.",
            "UART_PAYLOAD_MISMATCH": "Check UART baud, framing settings, firmware payload, and TX/RX routing.",
            "FIRMWARE_PIN_MODE_MISMATCH": "Correct the firmware pinMode declaration to match the reviewed electrical role.",
            "FIRMWARE_PWM_MISSING": "Configure and drive the reviewed PWM pin in firmware before relying on the circuit output.",
            "FIRMWARE_PROTOCOL_MISMATCH": "Initialize the required bus in firmware and verify it matches the selected circuit blueprint.",
            "FIRMWARE_TRACE_MISMATCH": "Check the flashed firmware, output pin mapping, and logic-analyzer channel mapping; the measured level contradicts the source intent.",
            "POWER_DOMAIN_OUT_OF_RANGE": "Use the reviewed voltage rail or insert an appropriate regulator or level shifter.",
            "UART_LINES_SHORTED": "Cross TX to RX between devices; do not join TX and RX on one conductor.",
            "RC_TIME_OUT_OF_RANGE": "Change the reviewed resistor or capacitor value so the RC delay falls inside the required timing range.",
            "RC_VOLTAGE_OUT_OF_RANGE": "Correct the RC values or timing interval so the calculated capacitor voltage meets the required threshold.",
            "RC_TOLERANCE_OUT_OF_RANGE": "Choose tighter-tolerance RC parts or wider reviewed timing margins so all worst-case delays remain safe.",
            "MEASUREMENT_OUT_OF_RANGE": "Correct the supply, load, firmware output, or component values until the measured electrical value is in range.",
            "PWM_OUT_OF_RANGE": "Correct the PWM firmware frequency or duty cycle, then verify it with the logic analyzer again.",
            "I2C_DEVICE_NO_ACK": "Check sensor power, common ground, SDA/SCL routing, pull-ups, and the configured I2C address.",
            "LOGIC_LEVEL_OVERVOLTAGE": "Add a reviewed level shifter or use the destination-compatible voltage domain before reconnecting the signal.",
            "LOGIC_LEVEL_UNDERVOLTAGE": "Use a level shifter or a driver that meets the destination HIGH threshold.",
            "REGULATOR_INPUT_OVERVOLTAGE": "Reduce the regulator input voltage or choose a regulator rated for the source voltage.",
            "REGULATOR_DROPOUT": "Increase input headroom or choose a lower-dropout regulator.",
            "MOSFET_GATE_UNDERDRIVEN": "Use a logic-level MOSFET or gate driver rated for the available control voltage.",
            "BJT_BASE_UNDERDRIVEN": "Reduce the base resistor or use a driver stage that provides the required saturation current.",
            "TRANSISTOR_CURRENT_LIMIT_EXCEEDED": "Use a driver/transistor with an adequate continuous current rating and thermal margin.",
            "SPICE_NODE_OUT_OF_RANGE": "Correct the reviewed SPICE circuit values or wiring until every required operating-point node is inside its safe range.",
            "SPICE_OPERATING_POINT_FAILED": "Correct the reviewed SPICE template or circuit topology, then repeat the deterministic operating-point check.",
            "SPICE_TRANSIENT_MEASUREMENT_OUT_OF_RANGE": "Correct the switching/timing circuit until each reviewed transient measurement is within its required range.",
            "SPICE_AC_MEASUREMENT_OUT_OF_RANGE": "Correct the filter or amplifier values until each reviewed AC measurement is within range.",
            "CURRENT_BUDGET_EXCEEDED": "Reduce simultaneous load current or use a reviewed supply/driver with enough derated continuous-current headroom.",
            "POWER_SEQUENCE_POWER_NOT_GOOD": "Fix the supply, regulator, or power-enable path before attempting module communication.",
            "POWER_SEQUENCE_ORDER_VIOLATION": "Correct the reviewed power/reset/enable order or increase the required settling delay.",
            "POWER_SEQUENCE_SIGNAL_MISSING": "Check the reset, enable, or data-control firmware and wiring; its required captured transition is missing.",
            "ADC_INPUT_OVERVOLTAGE": "Add a reviewed divider, clamp, or lower reference so the analog input cannot exceed the ADC limit.",
            "ADC_CODE_INVALID": "Check ADC resolution configuration, firmware data handling, and the captured measurement source.",
            "ADC_MEASUREMENT_OUT_OF_RANGE": "Check sensor supply, divider/gain values, ADC reference, and expected sensor operating range.",
            "CLOCK_FREQUENCY_OUT_OF_RANGE": "Correct the clock source, firmware timer, divider, or oscillator component values.",
            "CLOCK_JITTER_EXCEEDED": "Improve the clock source, grounding, supply stability, or timing configuration before trusting the digital circuit.",
            "CLOCK_DUTY_OUT_OF_RANGE": "Correct the clock/PWM timing configuration or driver circuitry to meet the reviewed duty-cycle range.",
            "THERMAL_DERATING_EXCEEDED": "Reduce dissipation, improve cooling, or select a component/driver with enough reviewed thermal margin.",
            "OP_AMP_COMMON_MODE_OUT_OF_RANGE": "Change the input bias, supply rails, or op-amp so both inputs remain inside the reviewed common-mode range.",
            "OP_AMP_OUTPUT_OUT_OF_RANGE": "Adjust the gain/bias or use rails and an op-amp that support the required output swing.",
            "LED_CURRENT_LIMITER_MISSING": "Add a correctly rated series resistor before powering the LED.",
        }
        default = "Correct the declared component value, topology, or measured operating condition, then rerun deterministic verification."
        return [{"code": finding["code"], "severity": finding["severity"], "likely_cause": finding["message"],
                 "recommended_action": actions.get(finding["code"], default)} for finding in findings[:5]]
