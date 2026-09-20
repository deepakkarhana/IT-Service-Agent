"""Loads the supplied data pack and keeps prototype-generated records.

The data pack files under ``data/`` are treated as read-only source of truth.
Anything the agent creates at runtime (new tickets, audit events) is written to
``data/runtime/`` so the two can never be confused.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .config import DATA_DIR, RUNTIME_DIR
from .models import AuditEvent, Ticket

# Prototype-generated ticket IDs start here and are deliberately not in the
# TK-10xx range used by the data pack, so a demo ticket is obvious at a glance.
FIRST_GENERATED_TICKET_NUMBER = 1001


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


class DataStore:
    def __init__(self, data_dir: Path = DATA_DIR, runtime_dir: Path = RUNTIME_DIR):
        self.data_dir = Path(data_dir)
        self.runtime_dir = Path(runtime_dir)
        # A hosted container may have a read-only filesystem. The agent still
        # works in that case - records live in memory for the session - so this
        # must never prevent the app from starting.
        self.persistence_enabled = True
        try:
            self.runtime_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            self.persistence_enabled = False
        self._lock = threading.Lock()

        self.policies: list[dict[str, Any]] = _read_json(
            self.data_dir / "knowledge_base.json"
        )["policies"]
        self.requests: list[dict[str, Any]] = _read_json(
            self.data_dir / "employee_requests.json"
        )["requests"]
        self.data_pack_tickets: list[dict[str, Any]] = _read_json(
            self.data_dir / "tickets.json"
        )["tickets"]

        self._policy_index = {p["id"]: p for p in self.policies}
        self.generated_tickets: list[Ticket] = []
        self.audit_log: list[AuditEvent] = []
        self._load_runtime()

    # ------------------------------------------------------------------ data
    def policy(self, policy_id: str) -> dict[str, Any]:
        try:
            return self._policy_index[policy_id]
        except KeyError as exc:  # pragma: no cover - guards against typos
            raise KeyError(f"Unknown policy id: {policy_id}") from exc

    def policy_point(self, policy_id: str, index: int) -> dict[str, str]:
        """Return one key point *verbatim* from the knowledge base.

        Every policy sentence the employee sees goes through this function, so
        the wording can always be traced back to ``data/knowledge_base.json``.
        """
        policy = self.policy(policy_id)
        return {"source_id": policy_id, "text": policy["key_points"][index]}

    def policy_points(self, policy_id: str, indexes: list[int]) -> list[dict[str, str]]:
        return [self.policy_point(policy_id, i) for i in indexes]

    def request(self, request_id: str) -> Optional[dict[str, Any]]:
        return next(
            (r for r in self.requests if r["request_id"] == request_id), None
        )

    def all_tickets(self) -> list[dict[str, Any]]:
        """Data-pack tickets plus anything this prototype created."""
        generated = [
            {**t.model_dump(), "related_policy": t.source_policy}
            for t in self.generated_tickets
        ]
        return [
            {**t, "origin": t.get("origin", "data_pack")}
            for t in self.data_pack_tickets
        ] + generated

    # -------------------------------------------------------------- mutation
    def next_ticket_id(self) -> str:
        return f"NEW-{FIRST_GENERATED_TICKET_NUMBER + len(self.generated_tickets)}"

    def add_ticket(self, ticket: Ticket) -> None:
        with self._lock:
            self.generated_tickets.append(ticket)
            self._persist_tickets()

    def add_audit_events(self, events: list[AuditEvent]) -> None:
        with self._lock:
            self.audit_log.extend(events)
            self._persist_audit()

    def reset_runtime(self) -> None:
        """Clear prototype-generated records (used by tests and the UI reset)."""
        with self._lock:
            self.generated_tickets = []
            self.audit_log = []
            self._persist_tickets()
            self._persist_audit()

    # ----------------------------------------------------------- persistence
    @property
    def _tickets_path(self) -> Path:
        return self.runtime_dir / "generated_tickets.json"

    @property
    def _audit_path(self) -> Path:
        return self.runtime_dir / "audit_log.json"

    def _write_json(self, path: Path, payload: Any) -> None:
        """Best-effort write. A read-only filesystem disables persistence
        rather than breaking the interaction the user just had."""
        if not self.persistence_enabled:
            return
        try:
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError:
            self.persistence_enabled = False

    def _persist_tickets(self) -> None:
        self._write_json(self._tickets_path, [t.model_dump() for t in self.generated_tickets])

    def _persist_audit(self) -> None:
        self._write_json(self._audit_path, [e.model_dump() for e in self.audit_log])

    def _load_runtime(self) -> None:
        """Reload previously generated records; corrupt files are ignored."""
        try:
            if self._tickets_path.exists():
                self.generated_tickets = [
                    Ticket(**row) for row in json.loads(self._tickets_path.read_text("utf-8"))
                ]
        except Exception:
            self.generated_tickets = []
        try:
            if self._audit_path.exists():
                self.audit_log = [
                    AuditEvent(**row)
                    for row in json.loads(self._audit_path.read_text("utf-8"))
                ]
        except Exception:
            self.audit_log = []


_store: Optional[DataStore] = None


def get_store() -> DataStore:
    global _store
    if _store is None:
        _store = DataStore()
    return _store
