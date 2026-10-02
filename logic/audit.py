"""Append-only, hash-chained audit records for live verification sessions."""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
from threading import RLock
from typing import Any


class AuditError(ValueError):
    """Raised when an audit record or audit chain is invalid."""


class SessionAuditLog:
    """Local JSONL evidence log with tamper-evident ordering.

    This is an integrity check, not a substitute for a signed remote audit
    service: someone who can rewrite the whole file can also rebuild hashes.
    It does make accidental edits, truncation, and mid-stream modification
    detectable, while keeping an offline professor demonstration self-contained.
    """

    SCHEMA_VERSION = 1

    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def append(self, state: dict[str, Any], event: str = "graph_revision") -> dict[str, Any]:
        session_id = state.get("session_id")
        revision = state.get("revision")
        if not isinstance(session_id, str) or not session_id:
            raise AuditError("Audit state requires a session_id.")
        if not isinstance(revision, int) or revision < 0:
            raise AuditError("Audit state requires a non-negative integer revision.")
        if not isinstance(event, str) or not event:
            raise AuditError("Audit event must be a non-empty string.")
        with self._lock:
            path = self._path_for(session_id)
            previous_hash, sequence = self._tail(path, session_id)
            body = {
                "schema_version": self.SCHEMA_VERSION,
                "sequence": sequence + 1,
                "event": event,
                "previous_hash": previous_hash,
                "state": state,
            }
            record = body | {"hash": self._hash(body)}
            with path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            return record

    def verify(self, session_id: str) -> dict[str, Any]:
        path = self._path_for(session_id)
        if not path.exists():
            return {"status": "NOT_FOUND", "session_id": session_id, "records": 0}
        previous_hash = None
        records = 0
        try:
            with path.open(encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue
                    record = json.loads(line)
                    if record.get("schema_version") != self.SCHEMA_VERSION:
                        raise AuditError(f"Unsupported schema at line {line_number}.")
                    if record.get("sequence") != records + 1:
                        raise AuditError(f"Unexpected sequence at line {line_number}.")
                    state = record.get("state")
                    if not isinstance(state, dict) or state.get("session_id") != session_id:
                        raise AuditError(f"Session mismatch at line {line_number}.")
                    if not isinstance(state.get("revision"), int) or state["revision"] < 0:
                        raise AuditError(f"Invalid state revision at line {line_number}.")
                    supplied_hash = record.get("hash")
                    body = {key: value for key, value in record.items() if key != "hash"}
                    if record.get("previous_hash") != previous_hash or supplied_hash != self._hash(body):
                        raise AuditError(f"Audit chain mismatch at line {line_number}.")
                    previous_hash = supplied_hash
                    records += 1
        except (OSError, json.JSONDecodeError, AuditError) as error:
            return {"status": "INVALID", "session_id": session_id, "records": records, "message": str(error)}
        return {"status": "PASS", "session_id": session_id, "records": records, "tail_hash": previous_hash}

    def _path_for(self, session_id: str) -> Path:
        # UUIDs are generated locally, but reject separators so this utility is
        # safe even when called from a future API handler.
        if any(character in session_id for character in ("/", "\\", "..")):
            raise AuditError("Invalid session_id for audit path.")
        return self.directory / f"{session_id}.jsonl"

    @staticmethod
    def _hash(body: dict[str, Any]) -> str:
        encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        return sha256(encoded).hexdigest()

    @staticmethod
    def _tail(path: Path, session_id: str) -> tuple[str | None, int]:
        if not path.exists():
            return None, 0
        previous_hash, sequence = None, 0
        # Verify the existing chain before extending it; never append to a
        # corrupted history and make a possibly misleading record.
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                record = json.loads(line)
                body = {key: value for key, value in record.items() if key != "hash"}
                state = record.get("state")
                if (record.get("schema_version") != SessionAuditLog.SCHEMA_VERSION
                        or record.get("sequence") != sequence + 1
                        or not isinstance(state, dict) or state.get("session_id") != session_id
                        or record.get("previous_hash") != previous_hash
                        or record.get("hash") != SessionAuditLog._hash(body)):
                    raise AuditError(f"Cannot append to invalid audit chain at line {line_number}.")
                previous_hash = record["hash"]
                sequence = record.get("sequence", sequence)
        return previous_hash, sequence
