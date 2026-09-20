"""Scenario tests for the IT Service Agent.

These run in deterministic mode (``use_llm=False``), which is exactly the mode
the demo falls back to. Each test asserts four things where they apply:

* the **decision** the agent made,
* the **source** policy it cited,
* the **team** it routed to,
* that it gave **no unsupported answer** (no policy sentence that is not in the
  knowledge base, and no citation of a policy ID that does not exist).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.app.agent.orchestrator import ITServiceAgent  # noqa: E402
from backend.app.data_store import DataStore  # noqa: E402
from backend.app.models import Decision  # noqa: E402


@pytest.fixture(scope="module")
def agent() -> ITServiceAgent:
    return ITServiceAgent(DataStore())


def run(agent: ITServiceAgent, message: str):
    """Run the pipeline without writing to the runtime files."""
    return agent.handle(message, employee="Test Employee", persist=False, use_llm=False)


def source_ids(result) -> list[str]:
    return [s.id for s in result.sources]


# --------------------------------------------------------------- 1. lockout
def test_password_lockout_creates_ticket_for_manual_unlock(agent):
    result = run(agent, "I am locked out of my account. I tried my password 6 times.")
    assert result.decision == Decision.CREATE_TICKET
    assert "KB-01" in source_ids(result)
    assert result.assigned_team == "IT Support"
    assert result.understanding.entities.account_locked_out is True
    assert result.ticket is not None


def test_simple_password_reset_is_self_service(agent):
    result = run(agent, "I forgot my password, how do I reset it?")
    assert result.decision == Decision.RESOLVE
    assert "KB-01" in source_ids(result)
    assert result.ticket is None


# ------------------------------------------------------------- 2. guest wifi
def test_guest_wifi_resolves_without_a_ticket(agent):
    result = run(agent, "Can I get Wi-Fi access for a guest visiting tomorrow?")
    assert result.decision == Decision.RESOLVE
    assert source_ids(result) == ["KB-07"]
    assert result.ticket_required is False
    assert "front-desk kiosk" in " ".join(result.response.your_actions)


# -------------------------------------------------------- 3. VPN credentials
def test_expired_vpn_credentials_resolve_with_renewal(agent):
    result = run(agent, "My VPN stopped working. It says my credentials expired.")
    assert result.decision == Decision.RESOLVE
    assert "KB-02" in source_ids(result)
    assert result.understanding.entities.credentials_expired is True
    assert result.ticket is None


# --------------------------------------------------------- 4. contractor VPN
def test_contractor_vpn_routes_to_manager_approval(agent):
    result = run(agent, "I'm a contractor and I need VPN access to start work.")
    assert result.decision == Decision.ROUTE_TO_OTHER_FUNCTION
    assert "KB-02" in source_ids(result)
    assert result.assigned_team == "Manager approval"
    assert result.understanding.entities.employee_type == "contractor"


def test_vpn_request_without_employee_type_asks_for_it(agent):
    result = run(agent, "I need VPN access please.")
    assert result.decision == Decision.CLARIFY
    assert "full-time" in result.clarifying_question.lower()
    assert "Employment type (full-time employee or contractor)" in (
        result.understanding.missing_information
    )


# ------------------------------------------------------ 5. non-catalog software
def test_non_catalog_software_goes_to_it_security(agent):
    result = run(
        agent,
        "I need a data-analysis tool installed. It is not in the approved software catalog.",
    )
    assert result.decision == Decision.CREATE_TICKET
    assert "KB-04" in source_ids(result)
    assert result.assigned_team == "IT Security"
    assert "3 to 5 business days" in result.response.what_happens_next


def test_software_with_unknown_catalog_status_asks_first(agent):
    result = run(
        agent, "I would like approval to install a browser extension for productivity tracking."
    )
    assert result.decision == Decision.CLARIFY
    assert "catalog" in result.clarifying_question.lower()


# ---------------------------------------------------------------- 6. printer
def test_printer_first_line_is_self_service(agent):
    result = run(agent, "My printer is not printing anything.")
    assert result.decision == Decision.RESOLVE
    assert source_ids(result) == ["KB-05"]
    joined = " ".join(result.response.your_actions).lower()
    assert "queue" in joined and "spooler" in joined


def test_persisting_printer_fault_creates_ticket_and_asks_for_asset_tag(agent):
    result = run(
        agent,
        "The printer on the 3rd floor keeps showing a paper jam but there is no visible jam.",
    )
    assert result.decision == Decision.CREATE_TICKET
    assert "KB-05" in source_ids(result)
    assert "Printer asset tag" in result.understanding.missing_information


# --------------------------------------------------------- 7. mailbox quota
def test_full_mailbox_resolves_with_archiving(agent):
    result = run(agent, "My mailbox is full and I cannot send email any more.")
    assert result.decision == Decision.RESOLVE
    assert "KB-06" in source_ids(result)
    assert result.ticket is None


def test_quota_increase_needs_manager_approval(agent):
    result = run(agent, "Can you increase my mailbox quota? I need more storage.")
    assert result.decision == Decision.ROUTE_TO_OTHER_FUNCTION
    assert result.assigned_team == "Manager approval"
    assert any("50GB" in point.text for point in result.response.policy_says)


# ------------------------------------------------- 8. expense software routing
def test_expense_access_request_routes_to_finance_not_it(agent):
    result = run(agent, "I need access to the expense management system.")
    assert result.decision == Decision.ROUTE_TO_OTHER_FUNCTION
    assert source_ids(result) == ["KB-08"]
    assert result.assigned_team == "Finance"
    assert "IT" not in result.assigned_team


def test_expense_login_problem_stays_with_it(agent):
    result = run(
        agent,
        "I already have an expense account but I can't log in. It says invalid credentials.",
    )
    assert result.decision == Decision.CLARIFY
    assert result.assigned_team == "IT Support"
    assert result.assigned_team != "Finance"
    assert result.understanding.entities.existing_account is True


# ---------------------------------------------------- 9. security escalation
def test_phishing_is_always_escalated_to_security(agent):
    result = run(agent, "I think I received a phishing email asking for my password.")
    assert result.decision == Decision.ESCALATE
    assert source_ids(result) == ["KB-09"]
    assert result.assigned_team == "Security Team"
    assert result.priority == "HIGH"
    actions = " ".join(result.response.your_actions)
    assert "security@veridian-corp.example" in actions
    assert "not forward" in actions.lower()


def test_already_forwarded_phishing_is_recorded_without_inventing_steps(agent):
    result = run(
        agent,
        "I got a phishing email and I already forwarded it to a few teammates to warn them.",
    )
    assert result.decision == Decision.ESCALATE
    assert result.understanding.entities.already_forwarded is True
    assert "already forwarded" in (result.response.notice or "").lower()


def test_security_wording_cannot_be_reclassified_away(agent):
    """A security phrase wins even when the message looks like another topic."""
    result = run(agent, "My laptop is 3 years old and I think it has malware on it.")
    assert result.decision == Decision.ESCALATE
    assert result.assigned_team == "Security Team"


# ------------------------------------------------- 10. home-office equipment
def test_home_office_equipment_routes_through_manager_and_finance(agent):
    result = run(
        agent, "I work from home 4 days a week. Can I get a monitor for my home desk?"
    )
    assert result.decision == Decision.ROUTE_TO_OTHER_FUNCTION
    assert source_ids(result) == ["KB-10"]
    assert result.assigned_team == "Manager approval, then Finance"
    assert result.understanding.entities.remote_days_per_week == 4


def test_home_office_without_remote_days_asks_for_them(agent):
    result = run(agent, "Can I get a monitor for my home office?")
    assert result.decision == Decision.CLARIFY
    assert "days per week" in result.clarifying_question


# ------------------------------------------- 11. laptop replacement ambiguity
def test_laptop_in_conflict_zone_escalates_and_names_the_conflict(agent):
    result = run(
        agent, "My laptop is 3.5 years old and completely dead. Can I get a replacement?"
    )
    assert result.decision == Decision.ESCALATE
    assert set(source_ids(result)) == {"KB-03", "ASSET-POL"}
    assert result.policy_conflict is not None and result.policy_conflict.detected
    assert result.assigned_team == "Finance + IT Support (joint approval)"
    summary = result.policy_conflict.summary
    assert "3 years" in summary and "4-year" in summary
    # The agent must not claim one policy wins.
    assert "overrides" not in summary.lower() or "does not say which one overrides" in summary.lower()


def test_laptop_past_both_thresholds_has_no_conflict(agent):
    result = run(agent, "My laptop is 5 years old, can I get a replacement?")
    assert result.decision == Decision.CREATE_TICKET
    assert result.assigned_team == "IT Support"
    assert result.policy_conflict is None


def test_unverified_symptom_is_not_over_escalated(agent):
    """A 2-year-old flickering screen gets a diagnostic, not an escalation."""
    result = run(
        agent,
        "My laptop screen is flickering. The laptop is 2 years old. "
        "I am not sure if this needs a repair or a replacement.",
    )
    assert result.decision == Decision.CREATE_TICKET
    assert result.assigned_team == "IT Support"
    assert result.priority == "LOW"
    assert "verified" in (result.response.notice or "").lower()


def test_laptop_replacement_without_age_asks_for_it(agent):
    result = run(agent, "Can I get a laptop replacement?")
    assert result.decision == Decision.CLARIFY
    assert "how old" in result.clarifying_question.lower()


# --------------------------------------------------------------- 12. vagueness
def test_vague_request_asks_what_is_broken_and_guesses_nothing(agent):
    result = run(agent, "hey can you help, its not working")
    assert result.decision == Decision.CLARIFY
    assert result.sources == []
    assert result.ticket is None
    question = result.clarifying_question.lower()
    assert "system" in question and "error" in question
    # It must not have guessed a specific topic.
    for guess in ("vpn", "laptop", "password", "printer"):
        assert guess not in question


def test_request_with_no_matching_policy_is_escalated_not_answered(agent):
    result = run(agent, "My office chair is broken and the wheel fell off.")
    assert result.decision == Decision.ESCALATE
    assert result.sources == []
    assert result.response.policy_says == []
    assert "don't have enough information" in (result.response.notice or "")


def test_privileged_access_has_no_policy_and_is_escalated(agent):
    result = run(agent, "I need admin access to the finance reporting server.")
    assert result.decision == Decision.ESCALATE
    assert result.priority == "HIGH"
    assert result.sources == []
    assert result.response.policy_says == []
    # TK-1050 may be shown, but only labelled as precedent, never as policy.
    assert "precedent" in (result.response.notice or "").lower()


# ----------------------------------------------------- cross-cutting guarantees
ALL_MESSAGES = [
    "Can I get Wi-Fi access for a guest visiting tomorrow?",
    "I think I received a phishing email asking for my password.",
    "hey can you help, its not working",
    "I need access to the expense management system.",
    "My laptop is 3.5 years old and completely dead. Can I get a replacement?",
    "I'm a contractor and I need VPN access.",
    "I already have an expense account but I can't log in.",
    "I am locked out of my account after 6 attempts.",
    "My mailbox is full and I cannot send email.",
    "I need admin access to the finance reporting server.",
    "The printer keeps showing a paper jam but there is no visible jam.",
    "I work from home 4 days a week, can I get a monitor?",
]


@pytest.mark.parametrize("message", ALL_MESSAGES)
def test_every_policy_sentence_shown_exists_verbatim_in_the_knowledge_base(agent, message):
    """The core anti-hallucination guarantee."""
    result = run(agent, message)
    store = agent.store
    for point in result.response.policy_says:
        policy = store.policy(point.source_id)
        assert point.text in policy["key_points"], (
            f"{point.source_id} sentence not found verbatim in the knowledge base: "
            f"{point.text!r}"
        )


@pytest.mark.parametrize("message", ALL_MESSAGES)
def test_every_cited_source_id_exists(agent, message):
    result = run(agent, message)
    known = {p["id"] for p in agent.store.policies}
    assert {s.id for s in result.sources} <= known
    if result.ticket:
        assert set(result.ticket.source_policy) <= known


@pytest.mark.parametrize("message", ALL_MESSAGES)
def test_every_interaction_produces_a_complete_audit_trail(agent, message):
    result = run(agent, message)
    stages = [event.stage for event in result.audit_events]
    assert stages[0] == "request_received"
    assert stages[-1] == "audit_recorded"
    for required in ("understanding", "retrieval", "policy_evaluation", "decision",
                     "response_generated"):
        assert required in stages
    for event in result.audit_events:
        assert event.interaction_id == result.interaction_id
        assert event.timestamp


def test_empty_message_is_rejected_cleanly(agent):
    with pytest.raises(ValueError):
        run(agent, "   ")


def test_closed_tickets_are_labelled_as_history_not_policy(agent):
    result = run(agent, "I need admin access to the finance reporting server.")
    closed = [t for t in result.related_tickets if not t.active]
    assert closed, "expected TK-1050 as historical context"
    for ticket in closed:
        assert "not policy" in ticket.note.lower()
