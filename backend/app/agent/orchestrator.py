"""The agent pipeline.

    employee message
        -> Step 1  understand   (rules, optionally assisted by an LLM)
        -> Step 2  retrieve     (policies + ticket context)
        -> Step 3  check policy |
        -> Step 4  decide       | deterministic policy engine
        -> Step 5  respond      (templates + verbatim policy text)
        -> Step 6  ticket       (only when the decision calls for one)
        -> Step 7  audit        (every stage recorded)

The orchestrator owns the order of those steps and the audit trail. It holds no
policy knowledge of its own.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from ..data_store import DataStore
from ..models import (
    AgentResult,
    AuditEvent,
    CATEGORY_BY_TOPIC,
    Decision,
    Entities,
    Ticket,
    Topic,
    Understanding,
)
from ..retrieval import PolicyRetriever, retrieve_related_tickets
from . import llm as llm_module
from .policy_engine import evaluate
from .responder import build_response, rule_based_summary
from .understanding import rule_based_understanding, safety_override_topic

MAX_ISSUE_DETAIL = 240


class _AuditRecorder:
    """Collects audit events with strictly increasing timestamps."""

    def __init__(self, interaction_id: str, employee: str, request_id: Optional[str]):
        self.interaction_id = interaction_id
        self.employee = employee
        self.request_id = request_id
        self.events: list[AuditEvent] = []
        self._clock = datetime.now(timezone.utc)

    def add(self, stage: str, detail: str, **data) -> None:
        self._clock += timedelta(milliseconds=1)
        self.events.append(
            AuditEvent(
                timestamp=self._clock.isoformat(timespec="milliseconds"),
                interaction_id=self.interaction_id,
                request_id=self.request_id,
                employee=self.employee,
                stage=stage,
                detail=detail,
                data=data,
            )
        )


class ITServiceAgent:
    def __init__(self, store: DataStore):
        self.store = store
        self.retriever = PolicyRetriever(store)

    # ------------------------------------------------------------------ steps
    def _understand(
        self, message: str, audit: _AuditRecorder, use_llm: bool = True
    ) -> tuple[Understanding, str, str, Optional[str]]:
        """Step 1. Returns (understanding, mode, mode_detail, llm_summary)."""
        rules = rule_based_understanding(message)
        outcome = (
            llm_module.extract_understanding(message)
            if use_llm
            else llm_module.LLMOutcome(None, False, "Rules-only run (queue preview).")
        )

        if not outcome.ok or outcome.understanding is None:
            audit.add(
                "understanding",
                f"Classified by deterministic rules as '{rules.topic.value}'.",
                topic=rules.topic.value,
                mode="fallback",
                reason=outcome.detail,
            )
            return rules, "fallback", outcome.detail, None

        llm_u = outcome.understanding
        final = rules.model_copy(deep=True)
        final.topic = llm_u.topic
        final.intent = llm_u.intent or rules.intent
        final.urgency_stated = rules.urgency_stated or llm_u.urgency_stated
        # Regex-extracted facts win; the model only fills the gaps it found.
        final.entities = rules.entities.merged_with(llm_u.entities)
        final.classification_source = "llm"

        # Hard safety override: KB-09 / privileged access are decided in code.
        override = safety_override_topic(message)
        if override is not None and final.topic != override:
            audit.add(
                "safety_override",
                (
                    f"Model proposed '{llm_u.topic.value}'. Deterministic safety rule "
                    f"forced '{override.value}'."
                ),
                model_topic=llm_u.topic.value,
                enforced_topic=override.value,
            )
            final.topic = override
            final.classification_source = "llm+safety-override"

        final.category = CATEGORY_BY_TOPIC[final.topic]
        final.is_vague = rules.is_vague and final.topic == Topic.UNKNOWN
        audit.add(
            "understanding",
            f"Classified as '{final.topic.value}' ({final.classification_source}).",
            topic=final.topic.value,
            mode="llm",
            model=llm_module.settings.llm_model,
        )
        return final, "llm", outcome.detail, llm_u.summary or None

    def _build_ticket(
        self, result_parts: dict, understanding: Understanding, outcome
    ) -> Ticket:
        """Step 6. Prototype ticket IDs are deliberately prefixed 'NEW-'."""
        message: str = result_parts["message"]
        detail = message.strip()
        if len(detail) > MAX_ISSUE_DETAIL:
            detail = detail[: MAX_ISSUE_DETAIL - 1].rstrip() + "…"
        return Ticket(
            ticket_id=self.store.next_ticket_id(),
            employee=result_parts["employee"],
            issue_summary=understanding.intent or "IT request",
            issue_detail=detail,
            category=understanding.category,
            priority=outcome.priority,
            decision=outcome.decision,
            next_action=outcome.next_action,
            status=outcome.ticket_status or "Open",
            assigned_team=outcome.assigned_team,
            source_policy=outcome.source_policy_ids,
            created_at=result_parts["created_at"],
            active=True,
            origin="prototype_generated",
            source_request_id=result_parts["request_id"],
        )

    # ------------------------------------------------------------------- main
    def handle(
        self,
        message: str,
        employee: str = "Employee (demo user)",
        request_id: Optional[str] = None,
        persist: bool = True,
        use_llm: bool = True,
    ) -> AgentResult:
        message = (message or "").strip()
        if not message:
            raise ValueError("Empty request: there is nothing to act on.")

        interaction_id = f"INT-{uuid.uuid4().hex[:8].upper()}"
        effective_request_id = request_id or f"RQ-{uuid.uuid4().hex[:6].upper()}"
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

        audit = _AuditRecorder(interaction_id, employee, effective_request_id)
        audit.add(
            "request_received",
            f"Request received from {employee}.",
            characters=len(message),
            from_queue=bool(request_id),
        )

        # Step 1 ------------------------------------------------------------
        understanding, mode, mode_detail, llm_summary = self._understand(
            message, audit, use_llm=use_llm
        )

        # Step 2 ------------------------------------------------------------
        sources = self.retriever.retrieve(message, understanding.topic)
        if sources:
            audit.add(
                "retrieval",
                "Retrieved " + ", ".join(s.id for s in sources) + ".",
                sources=[{"id": s.id, "score": s.match_score, "relevance": s.relevance} for s in sources],
            )
        else:
            top = self.retriever.score_all(message)[:1]
            audit.add(
                "retrieval",
                "No policy in the knowledge base governs this request.",
                best_lexical_match=(
                    {"id": top[0][0], "score": top[0][1]} if top else None
                ),
            )

        related = retrieve_related_tickets(self.store, understanding.topic)
        if related:
            audit.add(
                "ticket_context",
                "Ticket context: " + ", ".join(t.ticket_id for t in related) + ".",
                active=[t.ticket_id for t in related if t.active],
                history=[t.ticket_id for t in related if not t.active],
            )

        # Steps 3 + 4 --------------------------------------------------------
        outcome = evaluate(
            self.store,
            understanding.topic,
            understanding.entities,
            message,
            understanding.is_vague,
        )
        understanding.risk_level = outcome.risk_level
        understanding.missing_information = outcome.missing_information

        audit.add("policy_evaluation", outcome.decision_reason,
                  policies_applied=outcome.source_policy_ids)
        if outcome.conflict and outcome.conflict.detected:
            audit.add(
                "policy_conflict",
                "Conflicting guidance detected between "
                + " and ".join(sorted({p.source_id for p in outcome.conflict.positions}))
                + ". Not resolved by the agent.",
                sources=sorted({p.source_id for p in outcome.conflict.positions}),
            )
        audit.add(
            "decision",
            f"Decision: {outcome.decision.value} | priority {outcome.priority} | "
            f"assigned to {outcome.assigned_team}.",
            decision=outcome.decision.value,
            priority=outcome.priority,
            assigned_team=outcome.assigned_team,
        )

        # Step 5 --------------------------------------------------------------
        summary = llm_summary or rule_based_summary(understanding)
        understanding.summary = summary
        response = build_response(understanding, outcome, summary)
        audit.add(
            "response_generated",
            "Employee response generated from policy text."
            if outcome.policy_points
            else "Employee response generated - no policy text to cite.",
            policy_points=[p.source_id for p in outcome.policy_points],
        )

        # Step 6 --------------------------------------------------------------
        ticket: Optional[Ticket] = None
        if outcome.ticket_required:
            ticket = self._build_ticket(
                {
                    "message": message,
                    "employee": employee,
                    "created_at": created_at,
                    "request_id": effective_request_id,
                },
                understanding,
                outcome,
            )
            if persist:
                self.store.add_ticket(ticket)
            stage = (
                "escalation_raised"
                if outcome.decision == Decision.ESCALATE
                else "ticket_created"
            )
            audit.add(
                stage,
                f"{ticket.ticket_id} created for {outcome.assigned_team} "
                f"({ticket.status}).",
                ticket_id=ticket.ticket_id,
                status=ticket.status,
                source_policy=ticket.source_policy,
            )
        else:
            audit.add(
                "no_ticket_required",
                "No ticket raised - "
                + (
                    "waiting on information from the employee."
                    if outcome.decision == Decision.CLARIFY
                    else "resolved without IT action."
                ),
            )

        # Step 7 --------------------------------------------------------------
        audit.add("audit_recorded", "Interaction written to the audit trail.")
        if persist:
            self.store.add_audit_events(audit.events)

        return AgentResult(
            interaction_id=interaction_id,
            request_id=effective_request_id,
            employee=employee,
            employee_input=message,
            created_at=created_at,
            mode=mode,  # type: ignore[arg-type]
            mode_detail=mode_detail,
            understanding=understanding,
            decision=outcome.decision,
            decision_reason=outcome.decision_reason,
            risk_level=outcome.risk_level,
            priority=outcome.priority,
            assigned_team=outcome.assigned_team,
            next_action=outcome.next_action,
            clarifying_question=outcome.clarifying_question,
            policy_conflict=outcome.conflict,
            response=response,
            sources=sources,
            related_tickets=related,
            ticket_required=outcome.ticket_required,
            ticket=ticket,
            audit_events=audit.events,
        )


_agent: Optional[ITServiceAgent] = None


def get_agent(store: DataStore) -> ITServiceAgent:
    global _agent
    if _agent is None or _agent.store is not store:
        _agent = ITServiceAgent(store)
    return _agent
