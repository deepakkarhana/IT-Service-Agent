"""Steps 3 and 4 - Check policy, then decide.

This module is pure deterministic Python. Given a topic and the facts extracted
from the message, it returns exactly one decision plus the policy statements
that justify it.

Two rules hold everywhere in this file:

* every sentence of policy shown to the employee is fetched with
  ``store.policy_point(...)``, i.e. copied verbatim out of
  ``data/knowledge_base.json``. Nothing is paraphrased into a new rule.
* a fact that was not stated is never assumed. The engine either asks for it or
  explains the branches it can already distinguish.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from ..data_store import DataStore
from ..models import (
    Decision,
    Entities,
    PolicyConflict,
    PolicyPoint,
    PriorityLevel,
    RiskLevel,
    Topic,
)

# Routing labels. These come from the owning function named in the policy text
# itself (IT, IT Security, Security, Finance, manager) - no org unit has been
# invented. See docs/assumptions.md.
TEAM_IT = "IT Support"
TEAM_IT_SECURITY = "IT Security"
TEAM_SECURITY = "Security Team"
TEAM_FINANCE = "Finance"
TEAM_MANAGER = "Manager approval"
TEAM_MANAGER_FINANCE = "Manager approval, then Finance"
TEAM_FINANCE_IT = "Finance + IT Support (joint approval)"
TEAM_SELF_SERVICE = "No team required (self-service)"
TEAM_TRIAGE = "IT Support (human triage)"

SECURITY_MAILBOX = "security@veridian-corp.example"

PRIORITY_BY_RISK: dict[str, PriorityLevel] = {
    "low": "LOW",
    "medium": "MEDIUM",
    "high": "HIGH",
}


@dataclass
class PolicyOutcome:
    decision: Decision
    decision_reason: str
    risk_level: RiskLevel
    assigned_team: str
    next_action: str
    what_happens_next: str
    policy_points: list[PolicyPoint] = field(default_factory=list)
    employee_actions: list[str] = field(default_factory=list)
    clarifying_question: Optional[str] = None
    missing_information: list[str] = field(default_factory=list)
    ticket_required: bool = False
    ticket_status: str = ""
    conflict: Optional[PolicyConflict] = None
    notice: Optional[str] = None
    source_policy_ids: list[str] = field(default_factory=list)

    @property
    def priority(self) -> PriorityLevel:
        return PRIORITY_BY_RISK[self.risk_level]


def _points(store: DataStore, spec: list[tuple[str, int]]) -> list[PolicyPoint]:
    """Fetch (policy_id, key_point_index) pairs verbatim from the data pack."""
    return [PolicyPoint(**store.policy_point(pid, idx)) for pid, idx in spec]


def _ids(points: list[PolicyPoint], extra: Optional[list[str]] = None) -> list[str]:
    seen: list[str] = []
    for p in points:
        if p.source_id not in seen:
            seen.append(p.source_id)
    for pid in extra or []:
        if pid not in seen:
            seen.append(pid)
    return seen


# --------------------------------------------------------------------- topics
def _guest_wifi(store: DataStore) -> PolicyOutcome:
    pts = _points(store, [("KB-07", 0), ("KB-07", 1), ("KB-07", 2)])
    return PolicyOutcome(
        decision=Decision.RESOLVE,
        decision_reason=(
            "KB-07 makes guest Wi-Fi a self-service action that any employee can "
            "complete, and states explicitly that no IT ticket is required."
        ),
        risk_level="low",
        assigned_team=TEAM_SELF_SERVICE,
        next_action="Employee generates guest credentials at the front-desk kiosk.",
        what_happens_next=(
            "Nothing is needed from IT. You can complete this yourself, so no "
            "ticket has been raised."
        ),
        policy_points=pts,
        employee_actions=[
            "Generate the guest credentials at the front-desk kiosk.",
            "Give them to your visitor - they are valid for 24 hours, so generate "
            "them on the day of the visit.",
        ],
        source_policy_ids=_ids(pts),
    )


def _password(store: DataStore, ent: Entities) -> PolicyOutcome:
    if ent.account_locked_out:
        pts = _points(store, [("KB-01", 1), ("KB-01", 2)])
        attempts = (
            f" You reported {ent.failed_attempts} failed attempts."
            if ent.failed_attempts is not None
            else ""
        )
        return PolicyOutcome(
            decision=Decision.CREATE_TICKET,
            decision_reason=(
                "KB-01 states that an account locked after 5 failed attempts must be "
                f"unlocked manually by IT, so this cannot be self-served.{attempts}"
            ),
            risk_level="low",
            assigned_team=TEAM_IT,
            next_action="IT Support to unlock the account manually.",
            what_happens_next=(
                "A ticket has been raised for IT Support to unlock your account "
                "manually. No approval is required for this."
            ),
            policy_points=pts,
            employee_actions=[
                "Wait for IT Support to unlock the account.",
                "Once unlocked, set a new password through the self-service portal.",
            ],
            ticket_required=True,
            ticket_status="Open - pending IT Support",
            source_policy_ids=_ids(pts),
        )

    pts = _points(store, [("KB-01", 0), ("KB-01", 2)])
    return PolicyOutcome(
        decision=Decision.RESOLVE,
        decision_reason="KB-01 makes a password reset a self-service action with no approval required.",
        risk_level="low",
        assigned_team=TEAM_SELF_SERVICE,
        next_action="Employee resets the password via the self-service portal.",
        what_happens_next="You can complete this yourself, so no ticket has been raised.",
        policy_points=pts,
        employee_actions=["Reset your password using the self-service portal."],
        notice=(
            "If the account locks after 5 failed attempts, come back and IT will "
            "unlock it manually."
        ),
        source_policy_ids=_ids(pts),
    )


def _vpn(store: DataStore, ent: Entities) -> PolicyOutcome:
    if ent.credentials_expired:
        pts = _points(store, [("KB-02", 2), ("KB-02", 3)])
        return PolicyOutcome(
            decision=Decision.RESOLVE,
            decision_reason=(
                "KB-02 states VPN credentials expire every 90 days and that the "
                "employee renews them, which matches the expiry message reported."
            ),
            risk_level="low",
            assigned_team=TEAM_SELF_SERVICE,
            next_action="Employee renews the expired VPN credentials.",
            what_happens_next=(
                "This is the expected 90-day expiry rather than a fault, so no "
                "ticket has been raised. Renewing your credentials restores access."
            ),
            policy_points=pts,
            employee_actions=["Renew your VPN credentials, then reconnect."],
            source_policy_ids=_ids(pts),
        )

    if ent.new_access_request:
        if ent.employee_type == "contractor":
            pts = _points(store, [("KB-02", 1), ("KB-02", 2)])
            return PolicyOutcome(
                decision=Decision.ROUTE_TO_OTHER_FUNCTION,
                decision_reason=(
                    "You stated you are a contractor. KB-02 requires manager approval "
                    "through the access request form before a contractor receives VPN "
                    "access, so IT cannot provision it directly."
                ),
                risk_level="medium",
                assigned_team=TEAM_MANAGER,
                next_action=(
                    "Manager approval via the access request form, then IT Support "
                    "provisions VPN access."
                ),
                what_happens_next=(
                    "Your request has been recorded and routed for manager approval. "
                    "IT Support provisions the access once that approval is in place."
                ),
                policy_points=pts,
                employee_actions=[
                    "Submit the access request form for VPN access.",
                    "Ask your manager to approve that request.",
                ],
                ticket_required=True,
                ticket_status="Open - pending manager approval",
                source_policy_ids=_ids(pts),
            )
        if ent.employee_type == "full_time":
            pts = _points(store, [("KB-02", 0), ("KB-02", 2)])
            return PolicyOutcome(
                decision=Decision.CREATE_TICKET,
                decision_reason=(
                    "KB-02 says full-time employees receive VPN access automatically, "
                    "so no approval is needed. A ticket has been raised for IT Support "
                    "to confirm why the automatic access is not active."
                ),
                risk_level="low",
                assigned_team=TEAM_IT,
                next_action="IT Support to confirm automatic VPN provisioning.",
                what_happens_next=(
                    "No approval is required for you. IT Support will check the "
                    "automatic provisioning of your VPN access."
                ),
                policy_points=pts,
                employee_actions=[],
                ticket_required=True,
                ticket_status="Open - pending IT Support",
                source_policy_ids=_ids(pts),
            )

        pts = _points(store, [("KB-02", 0), ("KB-02", 1)])
        return PolicyOutcome(
            decision=Decision.CLARIFY,
            decision_reason=(
                "KB-02 sets a different path for full-time employees and contractors, "
                "and employment type was not stated. That single fact decides what "
                "happens next, so the agent asks rather than assumes."
            ),
            risk_level="low",
            assigned_team=TEAM_IT,
            next_action="Awaiting employment type from the employee.",
            what_happens_next="Once you confirm this, the correct path can be started.",
            policy_points=pts,
            clarifying_question=(
                "Are you a full-time employee or a contractor? Full-time employees "
                "receive VPN access automatically, while contractors need manager "
                "approval through the access request form."
            ),
            missing_information=["Employment type (full-time employee or contractor)"],
            source_policy_ids=_ids(pts),
        )

    pts = _points(store, [("KB-02", 2), ("KB-02", 3)])
    return PolicyOutcome(
        decision=Decision.CREATE_TICKET,
        decision_reason=(
            "The message reports a VPN problem that is not a credential expiry and "
            "not a new access request. KB-02 does not describe troubleshooting steps "
            "for that, so it goes to IT Support rather than being answered from policy."
        ),
        risk_level="low",
        assigned_team=TEAM_IT,
        next_action="IT Support to investigate the VPN connectivity issue.",
        what_happens_next="A ticket has been raised for IT Support to look into it.",
        policy_points=pts,
        notice=(
            "The knowledge base covers VPN provisioning and the 90-day credential "
            "expiry. It does not cover other VPN faults, so this has not been "
            "answered from policy."
        ),
        ticket_required=True,
        ticket_status="Open - pending IT Support",
        source_policy_ids=_ids(pts),
    )


def _laptop(store: DataStore, ent: Entities, text: str) -> PolicyOutcome:
    age = ent.asset_age_years
    failure = ent.reported_hardware_failure
    wants_replacement = bool(
        re.search(
            r"replac\w*|refresh cycle|upgrade|"
            r"new (?:laptop|machine|device|computer|one)|"
            r"(?:get|issue) me a new",
            text,
            re.IGNORECASE,
        )
    )

    # A symptom with no replacement question: verify the hardware first.
    if not wants_replacement and failure is not True:
        return _laptop_diagnostic(store, ent)

    if age is None:
        pts = _points(store, [("KB-03", 0), ("KB-03", 1), ("ASSET-POL", 0)])
        return PolicyOutcome(
            decision=Decision.CLARIFY,
            decision_reason=(
                "Eligibility depends on the age of the device and on whether a "
                "hardware failure has been verified. Neither was stated, and the two "
                "relevant sources set different age thresholds, so the agent asks "
                "instead of guessing."
            ),
            risk_level="low",
            assigned_team=TEAM_IT,
            next_action="Awaiting device age and failure verification status.",
            what_happens_next="Once you confirm these, the correct path can be started.",
            policy_points=pts,
            clarifying_question=(
                "How old is the laptop, counting from its date of issue, and has IT "
                "already confirmed a hardware failure?"
            ),
            missing_information=[
                "Laptop age from date of issue",
                "Whether a hardware failure has been verified by IT",
            ],
            source_policy_ids=_ids(pts),
        )

    # Both sources agree once the device is past the 4-year refresh cycle.
    if age >= 4:
        pts = _points(store, [("KB-03", 0), ("ASSET-POL", 0), ("KB-03", 2)])
        return PolicyOutcome(
            decision=Decision.CREATE_TICKET,
            decision_reason=(
                f"At {age:g} years the device is past the 3-year mark in KB-03 and past "
                "the 4-year refresh cycle in the Asset Management Policy Extract. Both "
                "sources agree, so there is no conflict to resolve."
            ),
            risk_level="medium",
            assigned_team=TEAM_IT,
            next_action="IT Support to process the replacement under the standard refresh cycle.",
            what_happens_next=(
                "A replacement ticket has been raised with IT Support. This sits "
                "inside the standard refresh cycle, so no Finance sign-off is needed."
            ),
            policy_points=pts,
            employee_actions=[
                "Raise the request at least 2 weeks before you need the replacement."
            ],
            ticket_required=True,
            ticket_status="Open - pending IT Support",
            source_policy_ids=_ids(pts),
        )

    # 3 <= age < 4: the two sources genuinely disagree.
    if age >= 3:
        spec = [("KB-03", 0), ("ASSET-POL", 0), ("ASSET-POL", 1)]
        if failure:
            spec.insert(1, ("KB-03", 1))
        pts = _points(store, spec)
        failure_note = ""
        if failure:
            failure_note = (
                " You also report that the device has failed completely. KB-03 allows "
                "earlier replacement for a *verified* hardware failure, so that route "
                "may apply once IT verifies the fault - but the verification has not "
                "happened yet."
            )
        conflict = PolicyConflict(
            detected=True,
            summary=(
                f"At {age:g} years this device is eligible under KB-03, which sets the "
                "replacement point at 3 years of service. The Asset Management Policy "
                "Extract sets a standard 4-year refresh cycle and requires Finance "
                "sign-off in addition to IT approval for replacement earlier than that "
                "cycle. The two sources give different guidance for this device and "
                "the supplied material does not say which one overrides the other, so "
                "the agent will not pick one." + failure_note
            ),
            positions=pts,
            resolution_path=(
                "Escalated to IT Support and Finance so a human applies the correct "
                "rule and records the sign-off."
            ),
        )
        return PolicyOutcome(
            decision=Decision.ESCALATE,
            decision_reason=(
                "Two retrieved sources give conflicting replacement guidance for a "
                f"device of {age:g} years. The agent does not have a rule that says "
                "which source wins, so it escalates instead of inventing one."
            ),
            risk_level="medium",
            assigned_team=TEAM_FINANCE_IT,
            next_action=(
                "IT Support and Finance to confirm which replacement rule applies and "
                "record the required approvals."
            ),
            what_happens_next=(
                "This has been escalated for joint IT and Finance review because the "
                "two policies differ for a device of this age. You will be told which "
                "rule applies once that is confirmed."
            ),
            policy_points=pts,
            employee_actions=[
                "Confirm the device's date of issue if you have it - that fixes the "
                "exact age both policies are measured against.",
            ]
            + (
                ["Hand the device to IT Support so the hardware failure can be verified."]
                if failure
                else []
            ),
            ticket_required=True,
            ticket_status="Escalated - pending IT and Finance review",
            conflict=conflict,
            source_policy_ids=_ids(pts),
        )

    # age < 4 with a reported total failure: the two sources combine rather than
    # contradict - KB-03 gives the early route, ASSET-POL adds the sign-off.
    if failure:
        pts = _points(store, [("KB-03", 1), ("ASSET-POL", 1), ("KB-03", 2)])
        return PolicyOutcome(
            decision=Decision.ESCALATE,
            decision_reason=(
                f"At {age:g} years the device is inside the 4-year refresh cycle, so any "
                "replacement is an early replacement. KB-03 allows that for a verified "
                "hardware failure, and the Asset Management Policy Extract requires "
                "Finance sign-off in addition to IT approval for it."
            ),
            risk_level="medium",
            assigned_team=TEAM_FINANCE_IT,
            next_action=(
                "IT Support to verify the hardware failure, then IT approval plus "
                "Finance sign-off for the early replacement."
            ),
            what_happens_next=(
                "This has been raised for IT to verify the failure and for the "
                "approvals an early replacement needs."
            ),
            policy_points=pts,
            employee_actions=[
                "Hand the device to IT Support so the hardware failure can be verified.",
                "Raise the replacement request at least 2 weeks before you need the device.",
            ],
            ticket_required=True,
            ticket_status="Escalated - pending IT verification and Finance sign-off",
            notice=(
                "These two sources combine here rather than contradict each other: "
                "KB-03 provides the earlier-replacement route for a verified hardware "
                "failure, and the Asset Management Policy Extract adds the Finance "
                "sign-off that any replacement outside the 4-year cycle requires. Note "
                "that KB-03 requires a *verified* failure - so far the failure is "
                "reported, not verified."
            ),
            source_policy_ids=_ids(pts),
        )

    return _laptop_diagnostic(store, ent)


def _laptop_diagnostic(store: DataStore, ent: Entities) -> PolicyOutcome:
    """A symptom that is not a confirmed failure. Verify before escalating."""
    pts = _points(store, [("KB-03", 1)])
    age = ent.asset_age_years
    symptom = ent.hardware_symptom or "the reported fault"
    notice = (
        "KB-03 allows an earlier replacement only for a *verified* hardware failure. "
        f"So far {symptom} is a reported symptom, not a verified failure, so the first "
        "step is a hardware check by IT Support rather than a replacement decision."
    )
    if age is not None and age < 4:
        pts = pts + _points(store, [("ASSET-POL", 1)])
        notice += (
            f" If IT does confirm a hardware failure, the device is {age:g} years old and "
            "therefore inside the 4-year refresh cycle, so an early replacement would "
            "also need Finance sign-off in addition to IT approval."
        )
    return PolicyOutcome(
        decision=Decision.CREATE_TICKET,
        decision_reason=(
            "A symptom has been reported but no hardware failure has been verified, so "
            "the supported next step is a diagnostic rather than a replacement or an "
            "escalation."
        ),
        risk_level="low",
        assigned_team=TEAM_IT,
        next_action="IT Support to run a hardware check and confirm whether this is a hardware failure.",
        what_happens_next=(
            "A ticket has been raised for IT Support to check the hardware. The "
            "outcome of that check decides whether this is a repair or a replacement."
        ),
        policy_points=pts,
        employee_actions=["Make the laptop available to IT Support for the hardware check."],
        missing_information=["Verification of whether this is a hardware failure"],
        ticket_required=True,
        ticket_status="Open - pending IT Support",
        notice=notice,
        source_policy_ids=_ids(pts),
    )


def _software(store: DataStore, ent: Entities) -> PolicyOutcome:
    name = ent.software_name or "the software"
    if ent.in_approved_catalog is True:
        pts = _points(store, [("KB-04", 0)])
        return PolicyOutcome(
            decision=Decision.RESOLVE,
            decision_reason="KB-04 allows approved catalog software to be self-installed.",
            risk_level="low",
            assigned_team=TEAM_SELF_SERVICE,
            next_action="Employee self-installs the approved catalog software.",
            what_happens_next="No ticket is needed - you can install this yourself.",
            policy_points=pts,
            employee_actions=["Install the software yourself from the approved catalog."],
            source_policy_ids=_ids(pts),
        )

    if ent.in_approved_catalog is False:
        pts = _points(store, [("KB-04", 1), ("KB-04", 2)])
        return PolicyOutcome(
            decision=Decision.CREATE_TICKET,
            decision_reason=(
                "The software was stated to be outside the approved catalog, and KB-04 "
                "requires an IT Security review for non-catalog software."
            ),
            risk_level="medium",
            assigned_team=TEAM_IT_SECURITY,
            next_action="IT Security to review the non-catalog software request.",
            what_happens_next=(
                "A ticket has been raised for IT Security review. KB-04 says that "
                "review takes 3 to 5 business days."
            ),
            policy_points=pts,
            employee_actions=[
                "Do not install the software until IT Security has completed the review."
            ],
            ticket_required=True,
            ticket_status="Open - pending IT Security review",
            source_policy_ids=_ids(pts),
        )

    pts = _points(store, [("KB-04", 0), ("KB-04", 1), ("KB-04", 2)])
    return PolicyOutcome(
        decision=Decision.CLARIFY,
        decision_reason=(
            "KB-04 splits into two different paths depending on whether the software "
            "is in the approved catalog, and that was not stated. The agent will not "
            "assume which side it falls on."
        ),
        risk_level="low",
        assigned_team=TEAM_IT,
        next_action="Awaiting confirmation of approved-catalog status.",
        what_happens_next="Once you confirm this, the correct path can be started.",
        policy_points=pts,
        clarifying_question=(
            f"Is {name} listed in the approved software catalog? Catalog software you "
            "can install yourself; anything outside the catalog needs an IT Security "
            "review first."
        ),
        missing_information=["Whether the software is in the approved catalog"],
        source_policy_ids=_ids(pts),
    )


def _printer(store: DataStore, ent: Entities) -> PolicyOutcome:
    if ent.already_tried_basic_steps or ent.asset_tag:
        pts = _points(store, [("KB-05", 2)])
        missing = [] if ent.asset_tag else ["Printer asset tag"]
        actions = (
            []
            if ent.asset_tag
            else ["Send the printer's asset tag - KB-05 requires it on the ticket."]
        )
        return PolicyOutcome(
            decision=Decision.CREATE_TICKET,
            decision_reason=(
                "The basic steps in KB-05 have already been tried or the fault "
                "persists, and KB-05 says to log a ticket with the printer asset tag "
                "at that point."
            ),
            risk_level="low",
            assigned_team=TEAM_IT,
            next_action="IT Support to investigate the printer fault on site.",
            what_happens_next="A ticket has been raised for IT Support.",
            policy_points=pts,
            employee_actions=actions,
            missing_information=missing,
            ticket_required=True,
            ticket_status="Open - pending IT Support",
            source_policy_ids=_ids(pts),
        )

    pts = _points(store, [("KB-05", 0), ("KB-05", 1), ("KB-05", 2)])
    return PolicyOutcome(
        decision=Decision.RESOLVE,
        decision_reason="KB-05 gives two self-service steps to try before a ticket is logged.",
        risk_level="low",
        assigned_team=TEAM_SELF_SERVICE,
        next_action="Employee works through the KB-05 troubleshooting steps.",
        what_happens_next=(
            "Try the two steps below first. If the problem is still there afterwards, "
            "come back with the printer asset tag and a ticket will be logged."
        ),
        policy_points=pts,
        employee_actions=["Check the printer queue.", "Restart the print spooler."],
        source_policy_ids=_ids(pts),
    )


def _mailbox(store: DataStore, ent: Entities) -> PolicyOutcome:
    if ent.requests_quota_increase:
        pts = _points(store, [("KB-06", 2), ("KB-06", 3), ("KB-06", 1)])
        return PolicyOutcome(
            decision=Decision.ROUTE_TO_OTHER_FUNCTION,
            decision_reason=(
                "KB-06 requires manager approval for any mailbox increase beyond the "
                "25GB default, so IT cannot grant this on its own."
            ),
            risk_level="medium",
            assigned_team=TEAM_MANAGER,
            next_action="Manager approval for the quota increase, then IT applies it.",
            what_happens_next=(
                "Your request has been recorded and routed for manager approval. The "
                "maximum quota is 50GB."
            ),
            policy_points=pts,
            employee_actions=[
                "Ask your manager to approve the mailbox increase.",
                "Archive old mail in the meantime - it may be enough on its own.",
            ],
            ticket_required=True,
            ticket_status="Open - pending manager approval",
            source_policy_ids=_ids(pts),
        )

    pts = _points(store, [("KB-06", 0), ("KB-06", 1), ("KB-06", 2), ("KB-06", 3)])
    return PolicyOutcome(
        decision=Decision.RESOLVE,
        decision_reason=(
            "KB-06 gives archiving as the standard action when a mailbox nears the "
            "25GB default quota, and that needs no approval."
        ),
        risk_level="low",
        assigned_team=TEAM_SELF_SERVICE,
        next_action="Employee archives old mail to free space under the 25GB quota.",
        what_happens_next=(
            "Archiving old mail should restore your ability to send. If you need more "
            "than the 25GB default, that route needs manager approval."
        ),
        policy_points=pts,
        employee_actions=["Archive old mail to bring the mailbox back under 25GB."],
        source_policy_ids=_ids(pts),
    )


def _expense(store: DataStore, ent: Entities) -> PolicyOutcome:
    if ent.existing_account:
        pts = _points(store, [("KB-08", 2), ("KB-08", 1)])
        return PolicyOutcome(
            decision=Decision.CLARIFY,
            decision_reason=(
                "The account already exists, so KB-08 puts this with IT as a technical "
                "sign-in problem rather than with Finance as an access request. IT "
                "needs the exact error before it can act."
            ),
            risk_level="low",
            assigned_team=TEAM_IT,
            next_action="Awaiting the exact sign-in error from the employee.",
            what_happens_next=(
                "This stays with IT Support - it is a login problem on an account you "
                "already have, not a new access request for Finance."
            ),
            policy_points=pts,
            clarifying_question=(
                "Could you share a screenshot of the exact error you see when you sign "
                "in to the expense tool, and confirm whether your password works on "
                "other company systems?"
            ),
            missing_information=["Exact error message or screenshot from the sign-in attempt"],
            source_policy_ids=_ids(pts),
        )

    pts = _points(store, [("KB-08", 0), ("KB-08", 1), ("KB-08", 2)])
    return PolicyOutcome(
        decision=Decision.ROUTE_TO_OTHER_FUNCTION,
        decision_reason=(
            "KB-08 states that access to the expense software is granted by Finance, "
            "not IT. This is an access request, so it does not belong to IT at all."
        ),
        risk_level="medium",
        assigned_team=TEAM_FINANCE,
        next_action="Finance to grant expense software access.",
        what_happens_next=(
            "This has been routed to Finance, who own access to the expense software. "
            "IT cannot grant it. Once the account exists, IT can help with any login "
            "or technical problem."
        ),
        policy_points=pts,
        employee_actions=["Raise the access request with Finance."],
        ticket_required=True,
        ticket_status="Routed to Finance - outside IT scope",
        source_policy_ids=_ids(pts),
    )


def _security(store: DataStore, ent: Entities) -> PolicyOutcome:
    pts = _points(store, [("KB-09", 0), ("KB-09", 1), ("KB-09", 2)])
    actions = [
        f"Report the email to {SECURITY_MAILBOX} immediately.",
        "Do not forward it to any other employees.",
    ]
    notice = None
    if ent.already_forwarded:
        actions[1] = "Do not forward it to anyone else from this point on."
        notice = (
            "You mentioned the email was already forwarded to other people. KB-09 is "
            "explicit that suspected phishing must not be forwarded to other "
            "employees, so that has been recorded in the escalation to give the "
            "Security Team the full picture. No further containment steps are "
            "suggested here because the supplied knowledge base does not define any."
        )
    return PolicyOutcome(
        decision=Decision.ESCALATE,
        decision_reason=(
            "KB-09 requires suspected phishing, malware or unauthorized access to be "
            "reported immediately to the Security Team. This is a fixed rule in code, "
            "so a security report is always escalated and is never resolved by the "
            "agent on its own."
        ),
        risk_level="high",
        assigned_team=TEAM_SECURITY,
        next_action="Security Team to investigate the reported incident.",
        what_happens_next=(
            "This has been escalated to the Security Team as a security incident and "
            "recorded with a high priority."
        ),
        policy_points=pts,
        employee_actions=actions,
        ticket_required=True,
        ticket_status="Escalated to Security - awaiting Security Team response",
        notice=notice,
        source_policy_ids=_ids(pts),
    )


def _privileged(store: DataStore) -> PolicyOutcome:
    return PolicyOutcome(
        decision=Decision.ESCALATE,
        decision_reason=(
            "The supplied knowledge base contains no policy covering administrative or "
            "privileged access. The agent will not approve, refuse or invent a process "
            "for it, so it goes to a human."
        ),
        risk_level="high",
        assigned_team=TEAM_IT_SECURITY,
        next_action="IT Security to review the privileged access request with the appropriate approver.",
        what_happens_next=(
            "This has been escalated for human review. Requests for elevated access "
            "are treated as high priority."
        ),
        policy_points=[],
        employee_actions=[
            "Add the business justification for the access if you have one - the "
            "reviewing team will ask for it.",
        ],
        ticket_required=True,
        ticket_status="Escalated - pending IT Security review",
        notice=(
            "Based on the available IT knowledge base, there is no policy covering "
            "administrative or privileged access requests, so this has not been "
            "answered from policy. A closed ticket in the history (TK-1050) was "
            "rejected for having no business justification - that is past precedent "
            "shown as context, not a rule from the knowledge base."
        ),
        source_policy_ids=[],
    )


def _wfh(store: DataStore, ent: Entities) -> PolicyOutcome:
    days = ent.remote_days_per_week
    if days is None:
        pts = _points(store, [("KB-10", 0), ("KB-10", 2)])
        return PolicyOutcome(
            decision=Decision.CLARIFY,
            decision_reason=(
                "KB-10 sets eligibility at more than 3 remote days per week and that "
                "number was not stated. It decides the whole outcome, so the agent asks."
            ),
            risk_level="low",
            assigned_team=TEAM_IT,
            next_action="Awaiting the number of remote working days per week.",
            what_happens_next="Once you confirm this, the correct path can be started.",
            policy_points=pts,
            clarifying_question=(
                "How many days per week do you work remotely? The home-office "
                "equipment allowance applies to more than 3 days per week."
            ),
            missing_information=["Number of remote working days per week"],
            source_policy_ids=_ids(pts),
        )

    if days > 3:
        pts = _points(store, [("KB-10", 0), ("KB-10", 1), ("KB-10", 2), ("KB-10", 3), ("KB-10", 4)])
        return PolicyOutcome(
            decision=Decision.ROUTE_TO_OTHER_FUNCTION,
            decision_reason=(
                f"You work remotely {days} days per week, which is above the "
                "more-than-3-days threshold in KB-10. KB-10 puts the sign-off with "
                "your manager and the processing with Finance - IT only ships the "
                "equipment after approval."
            ),
            risk_level="medium",
            assigned_team=TEAM_MANAGER_FINANCE,
            next_action=(
                "Manager sign-off, then Finance processes the allowance; IT Support "
                "ships the equipment after approval."
            ),
            what_happens_next=(
                "Your request has been recorded and routed for manager sign-off. "
                "Finance processes the one-time allowance after that, and IT ships "
                "the equipment once it is approved."
            ),
            policy_points=pts,
            employee_actions=["Ask your manager to sign off the home-office equipment request."],
            ticket_required=True,
            ticket_status="Open - pending manager sign-off",
            source_policy_ids=_ids(pts),
        )

    pts = _points(store, [("KB-10", 0)])
    return PolicyOutcome(
        decision=Decision.RESOLVE,
        decision_reason=(
            f"KB-10 sets eligibility at more than 3 remote days per week and you stated "
            f"{days}, so the allowance does not apply on the facts given."
        ),
        risk_level="low",
        assigned_team=TEAM_SELF_SERVICE,
        next_action="No action - the stated remote pattern is below the KB-10 threshold.",
        what_happens_next=(
            "On the information given the home-office equipment allowance does not "
            "apply. If your remote working pattern changes, come back and it can be "
            "looked at again."
        ),
        policy_points=pts,
        source_policy_ids=_ids(pts),
    )


def _vague() -> PolicyOutcome:
    return PolicyOutcome(
        decision=Decision.CLARIFY,
        decision_reason=(
            "The message does not name a system, device or application, so there is "
            "nothing to retrieve a policy for. The agent asks rather than guessing "
            "which issue it is."
        ),
        risk_level="low",
        assigned_team=TEAM_IT,
        next_action="Awaiting details of the affected system and the error seen.",
        what_happens_next="Once you tell me more, I can look up the right policy.",
        policy_points=[],
        clarifying_question=(
            "Sure - what isn't working? Please tell me which system, device or "
            "application you're having trouble with, and what error or behaviour "
            "you're seeing."
        ),
        missing_information=[
            "Affected system, device or application",
            "The error message or behaviour seen",
        ],
        source_policy_ids=[],
    )


def _unsupported() -> PolicyOutcome:
    return PolicyOutcome(
        decision=Decision.ESCALATE,
        decision_reason=(
            "Retrieval found no policy in the supplied knowledge base that covers this "
            "request, so there is no supported answer to give."
        ),
        risk_level="medium",
        assigned_team=TEAM_TRIAGE,
        next_action="IT Support to triage the request manually.",
        what_happens_next="A human from IT Support will pick this up.",
        policy_points=[],
        employee_actions=[],
        ticket_required=True,
        ticket_status="Open - pending human triage",
        notice=(
            "Based on the available IT knowledge base, I don't have enough information "
            "to safely resolve this request, so I'll route it for human review."
        ),
        source_policy_ids=[],
    )


# ---------------------------------------------------------------- entry point
def evaluate(
    store: DataStore, topic: Topic, ent: Entities, text: str, vague: bool
) -> PolicyOutcome:
    """Step 3 + Step 4: check policy, then return exactly one decision."""
    if topic == Topic.SECURITY_INCIDENT:
        return _security(store, ent)
    if topic == Topic.PRIVILEGED_ACCESS:
        return _privileged(store)
    if topic == Topic.GUEST_WIFI:
        return _guest_wifi(store)
    if topic == Topic.PASSWORD_RESET:
        return _password(store, ent)
    if topic == Topic.VPN_ACCESS:
        return _vpn(store, ent)
    if topic == Topic.LAPTOP_HARDWARE:
        return _laptop(store, ent, text)
    if topic == Topic.SOFTWARE_INSTALL:
        return _software(store, ent)
    if topic == Topic.PRINTER:
        return _printer(store, ent)
    if topic == Topic.MAILBOX_QUOTA:
        return _mailbox(store, ent)
    if topic == Topic.EXPENSE_SOFTWARE:
        return _expense(store, ent)
    if topic == Topic.WFH_EQUIPMENT:
        return _wfh(store, ent)
    return _vague() if vague else _unsupported()
