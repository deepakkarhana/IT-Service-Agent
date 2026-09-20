"""Step 5 - Respond.

The employee-facing answer is assembled from fixed sentence frames plus policy
text copied verbatim from the knowledge base. The LLM, when it is enabled, only
contributes the one-line restatement of the employee's own issue.

That split is the anti-hallucination control: a model cannot put a rule into the
answer, because the answer's policy section is not written by a model.
"""

from __future__ import annotations

from ..models import AgentResponseText, Entities, Understanding
from .policy_engine import PolicyOutcome


def _fact_phrases(ent: Entities) -> list[str]:
    """Human-readable list of what the employee actually stated."""
    facts: list[str] = []
    if ent.employee_type:
        facts.append(f"employment type: {ent.employee_type.replace('_', '-')}")
    if ent.asset_age_years is not None:
        facts.append(f"device age: {ent.asset_age_years:g} years")
    if ent.reported_hardware_failure is True:
        facts.append("device reported as not working at all")
    elif ent.reported_hardware_failure is False and ent.hardware_symptom:
        facts.append(f"reported symptom: {ent.hardware_symptom}")
    if ent.failed_attempts is not None:
        facts.append(f"{ent.failed_attempts} failed sign-in attempts")
    if ent.account_locked_out:
        facts.append("account locked out")
    if ent.credentials_expired:
        facts.append("credentials reported as expired")
    if ent.existing_account:
        facts.append("account already exists")
    elif ent.new_access_request:
        facts.append("new access request")
    if ent.in_approved_catalog is False:
        facts.append("software stated to be outside the approved catalog")
    elif ent.in_approved_catalog is True:
        facts.append("software stated to be in the approved catalog")
    if ent.requests_quota_increase:
        facts.append("asking for a quota increase")
    if ent.remote_days_per_week is not None:
        facts.append(f"works remotely {ent.remote_days_per_week} days per week")
    if ent.already_tried_basic_steps:
        facts.append("basic troubleshooting already tried")
    if ent.already_forwarded:
        facts.append("message already forwarded to other people")
    if ent.asset_tag:
        facts.append(f"asset tag {ent.asset_tag}")
    return facts


def rule_based_summary(understanding: Understanding) -> str:
    """Deterministic restatement used when the LLM is not available."""
    intent = understanding.intent or "An IT request"
    facts = _fact_phrases(understanding.entities)
    if facts:
        return f"{intent}. From your message: {', '.join(facts)}."
    return f"{intent}."


def build_response(
    understanding: Understanding, outcome: PolicyOutcome, summary: str
) -> AgentResponseText:
    """Assemble the four things the employee is told."""
    # The clarifying question gets its own highlighted box in the UI, so it is
    # deliberately not repeated in "what happens next" or "what you need to do".
    return AgentResponseText(
        understood=summary,
        policy_says=outcome.policy_points,
        what_happens_next=outcome.what_happens_next,
        your_actions=list(outcome.employee_actions),
        notice=outcome.notice,
    )
