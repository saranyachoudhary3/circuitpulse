"""Authoritative, conservative graph sessions for live circuit debugging."""

from __future__ import annotations

from collections import defaultdict, deque
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from threading import RLock
from typing import Any, Callable
from uuid import uuid4

from logic.audit import SessionAuditLog
from logic.catalog import PresetCatalog


class SessionError(ValueError):
    """Raised for invalid session and observation operations."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_connection(first: str, second: str) -> str:
    if not isinstance(first, str) or not first or not isinstance(second, str) or not second:
        raise SessionError("Connections require non-empty 'from' and 'to' terminals.")
    return " <-> ".join(sorted((first, second)))


@dataclass(frozen=True)
class Evidence:
    from_terminal: str
    to_terminal: str
    source: str
    confidence: float
    timestamp: str
    wire_color: str | None = None

    @property
    def key(self) -> str:
        return canonical_connection(self.from_terminal, self.to_terminal)

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.key, "from": self.from_terminal, "to": self.to_terminal,
                "source": self.source, "confidence": self.confidence, "timestamp": self.timestamp,
                "wire_color": self.wire_color}


class GraphSession:
    """A single-writer graph actor. Visual suggestions cannot bypass verification."""

    STABLE_WINDOW = 7
    STABLE_REQUIRED = 5
    AUTO_VERIFY_CONFIDENCE = 0.98
    # A jumper must be absent from five complete vision frames before a
    # vision-only edge is removed.  User confirmations are intentional
    # operator evidence and remain until the operator revokes them.
    ABSENCE_REQUIRED = 5
    
    SOURCE_CONFIDENCE = {"user_confirmed": 1.0, "instrumented": 0.95, "vision": 0.7}

    def __init__(self, preset: dict[str, Any], on_change: Callable[[dict[str, Any]], None] | None = None):
        self.id = str(uuid4())
        self.preset = deepcopy(preset)
        self.on_change = on_change
        self._lock = RLock()
        self.revision = 0
        # State revisions advance for every publication; graph revisions only
        # advance when accepted connectivity changes.  Deterministic evidence
        # binds to the latter so harmless repeated camera frames do not make a
        # valid electrical report stale.
        self.graph_revision = 0
        self.created_at = _now()
        self.updated_at = self.created_at
        self._histories: dict[str, deque[Evidence]] = defaultdict(lambda: deque(maxlen=self.STABLE_WINDOW))
        self._absence_counts: dict[str, int] = defaultdict(int)
        self._accepted: dict[str, Evidence] = {}
        self._rejected: set[str] = set()
        self._camera_available = True
        # A selected blueprint and a confirmed visual graph establish topology,
        # not component values or safe operating conditions.  A deterministic
        # netlist/simulator report for the current graph is required before
        # this actor can assert electrical PASS.
        self._deterministic_report: dict[str, Any] | None = None
        self._verification_graph_revision: int | None = None
        self._last_state: dict[str, Any] | None = None
        self._expected = {
            canonical_connection(connection["from"], connection["to"]): connection
            for connection in self.preset["connections"]
        }

    def observe(self, connections: list[dict[str, Any]]) -> dict[str, Any]:
        """Ingest one visual frame's terminal candidates without trusting it yet."""
        if not isinstance(connections, list):
            raise SessionError("'connections' must be a list.")
        with self._lock:
            before_topology = self._topology_signature_locked()
            seen: set[str] = set()
            for item in connections:
                try:
                    confidence = float(item.get("confidence", 0))
                except (TypeError, ValueError) as error:
                    raise SessionError("Connection confidence must be numeric.") from error
                if not 0 <= confidence <= 1:
                    raise SessionError("Connection confidence must be between 0 and 1.")
                evidence = Evidence(
                    from_terminal=item.get("from"), to_terminal=item.get("to"), source="vision",
                    confidence=confidence, timestamp=_now(), wire_color=item.get("wire_color"),
                )
                seen.add(evidence.key)
                if evidence.key not in self._rejected:
                    self._histories[evidence.key].append(evidence)
                    self._absence_counts[evidence.key] = 0
            # `connections` is a complete visual frame, not a delta.  This
            # prevents a removed wire from surviving indefinitely in the
            # observed graph.  A short absence (hand occlusion/motion) is
            # debounced, and explicit user confirmations are never discarded
            # here.
            for key in list(self._histories):
                if key in seen or key in self._accepted:
                    continue
                self._absence_counts[key] += 1
                if self._absence_counts[key] >= self.ABSENCE_REQUIRED:
                    self._histories.pop(key, None)
                    self._absence_counts.pop(key, None)
            if before_topology != self._topology_signature_locked():
                self.graph_revision += 1
                self._invalidate_verification_locked()
            self._camera_available = True
            return self._publish_locked()

    def set_camera_available(self, available: bool) -> dict[str, Any]:
        """Publish camera loss immediately; a prior PASS must never persist."""
        if not isinstance(available, bool):
            raise SessionError("Camera availability must be boolean.")
        with self._lock:
            if self._camera_available == available:
                return self.state()
            self._camera_available = available
            return self._publish_locked()

    def confirm(self, first: str, second: str, accepted: bool, wire_color: str | None = None) -> dict[str, Any]:
        with self._lock:
            before_topology = self._topology_signature_locked()
            key = canonical_connection(first, second)
            if accepted:
                self._accepted[key] = Evidence(first, second, "user_confirmed", 1.0, _now(), wire_color)
                self._rejected.discard(key)
            else:
                self._accepted.pop(key, None)
                self._rejected.add(key)
                self._histories.pop(key, None)
            if before_topology != self._topology_signature_locked():
                self.graph_revision += 1
                self._invalidate_verification_locked()
            return self._publish_locked()

    def attach_deterministic_verification(self, report: dict[str, Any], graph_revision: int,
                                          graph_fingerprint: str, terminal_nets: dict[str, str],
                                          netlist: dict[str, Any]) -> dict[str, Any]:
        """Attach a netlist/simulator result to exactly the graph it checked."""
        if not isinstance(report, dict) or report.get("status") not in {"PASS", "FAIL", "INDETERMINATE"}:
            raise SessionError("Verification report must have PASS, FAIL, or INDETERMINATE status.")
        if not isinstance(graph_revision, int):
            raise SessionError("graph_revision must be an integer.")
        with self._lock:
            if graph_revision != self.graph_revision:
                raise SessionError("Verification report is stale; rerun it against the current graph revision.")
            expected_fingerprint = self._graph_fingerprint_locked()
            if graph_fingerprint != expected_fingerprint:
                raise SessionError("Verification report does not bind to the current observed terminal graph.")
            self._validate_terminal_net_bindings_locked(terminal_nets, netlist)
            self._deterministic_report = deepcopy(report)
            self._verification_graph_revision = graph_revision
            return self._publish_locked()

    def add_instrumented_connection(self, first: str, second: str, adapter: str, wire_color: str | None = None) -> dict[str, Any]:
        """Add measured continuity as first-class graph evidence.

        This intentionally does not grant electrical PASS by itself: component
        values and operating limits still require a current deterministic
        report.  It does, however, remove the need to treat a proven conductor
        as merely a visual guess.
        """
        if not isinstance(adapter, str) or not adapter:
            raise SessionError("Instrument adapter must be a non-empty string.")
        with self._lock:
            before_topology = self._topology_signature_locked()
            key = canonical_connection(first, second)
            self._accepted[key] = Evidence(first, second, "instrumented", 1.0, _now(), wire_color)
            self._rejected.discard(key)
            if before_topology != self._topology_signature_locked():
                self.graph_revision += 1
                self._invalidate_verification_locked()
            return self._publish_locked()

    def _connection_confidence(self, key: str) -> float:
        evidence = self._accepted.get(key)
        if evidence is not None:
            source = evidence.source
        else:
            observed, pending = self._stable_evidence_locked()
            if key in observed:
                source = observed[key].source
            else:
                source = "vision"
        
        base = self.SOURCE_CONFIDENCE.get(source, 0.5)
        history = self._histories.get(key, deque())
        stability_bonus = min(0.2, len(history) / self.STABLE_WINDOW * 0.2)
        contradiction_penalty = 0.1 if key in self._rejected else 0.0
        return min(1.0, max(0.0, base + stability_bonus - contradiction_penalty))

    def state(self) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._last_state or self._build_state_locked())

    def _stable_evidence_locked(self) -> tuple[dict[str, Evidence], list[dict[str, Any]]]:
        stable: dict[str, Evidence] = dict(self._accepted)
        pending = []
        for key, history in self._histories.items():
            if key in self._rejected or key in stable or not history:
                continue
            latest = history[-1]
            enough_frames = len(history) >= self.STABLE_REQUIRED
            average = sum(item.confidence for item in history) / len(history)
            if enough_frames and average >= 0.70:
                stable[key] = Evidence(latest.from_terminal, latest.to_terminal, "vision", round(average, 3), latest.timestamp, latest.wire_color)
            else:
                pending.append({"id": key, "from": latest.from_terminal, "to": latest.to_terminal,
                                "frames": len(history), "confidence": round(average, 3), "reason": "awaiting_stability"})
        return stable, pending

    def _build_state_locked(self) -> dict[str, Any]:
        observed, pending = self._stable_evidence_locked()
        observed_keys = set(observed)
        expected_keys = set(self._expected)
        extra = sorted(observed_keys - expected_keys)
        missing = sorted(expected_keys - observed_keys)
        unverified = sorted(key for key in expected_keys & observed_keys
                            if observed[key].source != "user_confirmed" and observed[key].confidence < self.AUTO_VERIFY_CONFIDENCE)
        findings = []
        direct_short = next((key for key in extra if self._is_power_short(observed[key])), None)
        if direct_short:
            findings.append(self._finding("DIRECT_POWER_SHORT", "critical", "Direct positive-to-ground connection observed.", direct_short))
        for key in extra:
            if key != direct_short:
                findings.append(self._finding("EXTRA_CONNECTION", "error", "Observed connection is not part of the selected blueprint.", key))
        for key in missing:
            findings.append(self._finding("MISSING_CONNECTION", "info", "Required blueprint connection is not yet observed.", key))
        for item in pending:
            findings.append({"code": "AMBIGUOUS_CONNECTION", "severity": "warning", "message": "Connection is visible but not stable enough to trust.", "evidence": item})
        for key in unverified:
            findings.append(self._finding("UNCONFIRMED_CONNECTION", "warning", "Connection is stable but needs confirmation before electrical verification.", key))

        deterministic = self._deterministic_report or {
            "status": "INDETERMINATE", "reason": "No deterministic netlist/simulation result is attached to this graph revision.",
            "evidence_mode": "missing_deterministic_verification",
        }
        deterministic_status = deterministic["status"]
        for finding in deterministic.get("findings", []):
            if isinstance(finding, dict):
                findings.append({**finding, "source": "deterministic_verification"})

        if not self._camera_available:
            status = "REACQUIRING"
        elif direct_short or extra or deterministic_status == "FAIL":
            status = "FAULT"
        elif pending or unverified:
            status = "INDETERMINATE"
        elif missing:
            status = "INCOMPLETE"
        elif deterministic_status != "PASS":
            status = "INDETERMINATE"
        else:
            status = "PASS"

        observed_list = []
        overall_confidence = 1.0
        for key in sorted(observed_keys):
            d = observed[key].as_dict()
            conf = self._connection_confidence(key)
            d["confidence"] = conf
            overall_confidence = min(overall_confidence, conf)
            observed_list.append(d)

        graph = {"expected": [self._expected[key] for key in sorted(expected_keys)],
                 "observed": observed_list, "pending": pending}
        state = {
            "session_id": self.id, "revision": self.revision, "graph_revision": self.graph_revision,
            "graph_fingerprint": self._graph_fingerprint_from_observed(observed), "updated_at": self.updated_at,
            "overall_confidence": overall_confidence if observed_keys else 1.0,
            "preset": {"id": self.preset["id"], "name": self.preset["name"]},
            "status": status, "electrical_status": status,
            "evidence_mode": "confirmed_graph", "camera_status": "READY" if self._camera_available else "REACQUIRING",
            "graph": graph, "findings": findings,
            "diff": {"missing": missing, "extra": extra, "unverified": unverified},
            "deterministic_verification": {"status": deterministic_status, "graph_revision": self._verification_graph_revision,
                                             "evidence_mode": deterministic.get("evidence_mode"), "reason": deterministic.get("reason"),
                                             "root_causes": deterministic.get("root_causes", [])},
            "next_action": self._next_action(status, observed, missing, extra, pending, deterministic),
            "verification_note": self._verification_note(status),
        }
        return state

    def _publish_locked(self) -> dict[str, Any]:
        self.revision += 1
        self.updated_at = _now()
        state = self._build_state_locked()
        self._last_state = state
        if self.on_change:
            self.on_change(deepcopy(state))
        return deepcopy(state)

    def _next_action(self, status: str, observed: dict[str, Evidence], missing: list[str], extra: list[str], pending: list[dict[str, Any]], deterministic: dict[str, Any]) -> dict[str, Any] | None:
        if status == "REACQUIRING":
            return {"kind": "wait", "title": "Camera reacquiring", "instruction": "Keep the board still while the camera feed is restored.",
                    "reason": "No electrical verdict is valid while visual evidence is unavailable."}
        if status == "PASS":
            return {"kind": "complete", "title": "Blueprint verified", "instruction": "All required connections are present and verified.", "reason": "The confirmed graph matches the selected circuit blueprint."}
        direct = next((key for key in extra if self._is_power_short(observed[key])), None)
        if direct:
            return self._action("remove", direct, "Remove this wire immediately.", "It joins a positive rail directly to ground.")
        if extra:
            return self._action("remove", extra[0], "Remove or confirm this unexpected connection.", "It is not part of the selected circuit blueprint.")
        if pending:
            edge = pending[0]
            return {"kind": "confirm", "connection_id": edge["id"], "title": "Confirm ambiguous wire", "instruction": f"Confirm whether the wire connects {edge['from']} to {edge['to']}.", "reason": "The camera needs one confirmation before it can trust this endpoint."}
        if missing:
            order = {connection["id"]: index for index, connection in enumerate(self.preset.get("build_order", []))}
            selected = min(missing, key=lambda key: order.get(self._expected[key]["id"], len(order)))
            connection = self._expected[selected]
            color = connection.get("wire_color", "jumper")
            return {"kind": "add", "connection_id": selected, "title": connection.get("title", "Add required connection"),
                    "instruction": f"Connect the {color} wire from {connection['from']} to {connection['to']}.",
                    "reason": connection.get("purpose", "This is the next dependency in the selected circuit.")}
        if deterministic.get("status") == "FAIL":
            root_cause = next((item for item in deterministic.get("root_causes", []) if isinstance(item, dict)), None)
            return {"kind": "repair", "title": "Resolve deterministic electrical fault",
                    "instruction": root_cause.get("recommended_action") if root_cause else "Correct the netlist/simulator finding, then rerun verification for the current graph.",
                    "reason": root_cause.get("likely_cause") if root_cause else deterministic.get("summary") or deterministic.get("reason") or "Electrical safety verification failed."}
        if deterministic.get("status") != "PASS":
            return {"kind": "verify", "title": "Run electrical verification",
                    "instruction": "Submit the confirmed graph's netlist and measured component values for deterministic verification.",
                    "reason": "A camera-confirmed topology alone cannot prove component values, continuity, or operating safety."}
        return None

    def _action(self, kind: str, key: str, instruction: str, reason: str) -> dict[str, Any]:
        evidence = self._accepted.get(key)
        if evidence is None:
            evidence, _ = self._stable_evidence_locked()
            evidence = evidence[key]
        return {"kind": kind, "connection_id": key, "title": "Safety action" if kind == "remove" else "Required action",
                "instruction": f"{instruction} ({evidence.from_terminal} ↔ {evidence.to_terminal})", "reason": reason}

    @staticmethod
    def _finding(code: str, severity: str, message: str, key: str) -> dict[str, Any]:
        return {"code": code, "severity": severity, "message": message, "evidence": {"connection_id": key}}

    @staticmethod
    def _is_power_short(evidence: Evidence) -> bool:
        terminals = {evidence.from_terminal.lower(), evidence.to_terminal.lower()}
        positive = any(token.endswith(":5v") or token.endswith(":3v3") or token.endswith(":vcc") for token in terminals)
        ground = any(token.endswith(":gnd") or token.endswith(":ground") for token in terminals)
        return positive and ground

    @staticmethod
    def _verification_note(status: str) -> str:
        if status == "PASS":
            return "All blueprint connections are confirmed or meet the automatic confidence threshold."
        if status == "FAULT":
            return "A deterministic graph fault was found; do not power the circuit until it is resolved."
        if status == "REACQUIRING":
            return "Camera evidence is unavailable; the previous electrical verdict is intentionally withheld."
        return "Electrical verification is withheld until the graph is complete, unambiguous, and deterministically checked."

    def _invalidate_verification_locked(self) -> None:
        """A changed graph invalidates all derived electrical conclusions."""
        self._deterministic_report = None
        self._verification_graph_revision = None

    def _topology_signature_locked(self) -> frozenset[str]:
        """The only graph change that invalidates a topology-bound report."""
        observed, _ = self._stable_evidence_locked()
        return frozenset(observed)

    def _graph_fingerprint_locked(self) -> str:
        observed, _ = self._stable_evidence_locked()
        return self._graph_fingerprint_from_observed(observed)

    @staticmethod
    def _graph_fingerprint_from_observed(observed: dict[str, Evidence]) -> str:
        # Provenance and timestamp affect confidence/audit, not physical
        # topology.  The declared netlist must bind to this canonical edge set.
        content = [{"from": observed[key].from_terminal, "to": observed[key].to_terminal} for key in sorted(observed)]
        return sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    def _validate_terminal_net_bindings_locked(self, terminal_nets: dict[str, str], netlist: dict[str, Any]) -> None:
        if not isinstance(terminal_nets, dict) or not terminal_nets:
            raise SessionError("Verification requires terminal_nets for the current observed graph.")
        if not isinstance(netlist, dict):
            raise SessionError("Verification requires the submitted netlist object.")
        observed, _ = self._stable_evidence_locked()
        graph_terminals = {terminal for evidence in observed.values() for terminal in (evidence.from_terminal, evidence.to_terminal)}
        if set(terminal_nets) != graph_terminals or any(not isinstance(net, str) or not net for net in terminal_nets.values()):
            raise SessionError("terminal_nets must map exactly every observed graph terminal to a non-empty net name.")
        for evidence in observed.values():
            if terminal_nets[evidence.from_terminal] != terminal_nets[evidence.to_terminal]:
                raise SessionError(f"Observed wire {evidence.key} must map both terminals to the same declared net.")
        declared_nets = set()
        for component in netlist.get("components", []):
            if isinstance(component, dict) and isinstance(component.get("pins"), dict):
                declared_nets.update(net for net in component["pins"].values() if isinstance(net, str))
        for wire in netlist.get("wires", []):
            if isinstance(wire, dict):
                declared_nets.update(net for net in (wire.get("from"), wire.get("to")) if isinstance(net, str))
        missing = sorted(set(terminal_nets.values()) - declared_nets)
        if missing:
            raise SessionError(f"terminal_nets reference nets absent from the declared netlist: {missing}")


class SessionManager:
    def __init__(self, presets: PresetCatalog, on_change: Callable[[dict[str, Any]], None] | None = None,
                 audit_log: SessionAuditLog | None = None):
        self.presets = presets
        self.on_change = on_change
        self.audit_log = audit_log
        self._sessions: dict[str, GraphSession] = {}
        self._lock = RLock()
        # Before the capture worker supplies a frame, a new session must not
        # imply that the visual pipeline is healthy.
        self._camera_available = False

    def create(self, preset_id: str) -> dict[str, Any]:
        with self._lock:
            # Avoid emitting an unregistered creation state from the actor.
            session = GraphSession(self.presets.get(preset_id))
            if not self._camera_available:
                session.set_camera_available(False)
            self._sessions[session.id] = session
            session.on_change = self._publish
            state = session.state()
        self._record(state, "session_created")
        return state

    def get(self, session_id: str) -> GraphSession:
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise SessionError("Unknown session.")
        return session

    def count(self) -> int:
        with self._lock:
            return len(self._sessions)

    def set_camera_available(self, available: bool) -> None:
        """Fan a capture-state change out to all live sessions."""
        with self._lock:
            self._camera_available = available
            sessions = list(self._sessions.values())
        for session in sessions:
            session.set_camera_available(available)

    def verify_audit(self, session_id: str) -> dict[str, Any]:
        if self.audit_log is None:
            return {"status": "UNAVAILABLE", "message": "Audit logging is not configured."}
        self.get(session_id)  # Preserve the same unknown-session semantics as state routes.
        return self.audit_log.verify(session_id)

    def _publish(self, state: dict[str, Any]) -> None:
        self._record(state)
        if self.on_change:
            self.on_change(state)

    def _record(self, state: dict[str, Any], event: str = "graph_revision") -> None:
        if self.audit_log is not None:
            self.audit_log.append(state, event)
