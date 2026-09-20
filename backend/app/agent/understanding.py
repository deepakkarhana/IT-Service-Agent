"""Step 1 - Understand: deterministic classification and fact extraction.

This module never calls an LLM. It always runs, for three reasons:

* it is the fallback when no LLM key is configured or the API fails;
* it is the **safety override** - security incidents and privileged-access
  requests are detected by fixed patterns and cannot be reclassified by a model;
* explicit facts (numbers, "contractor", "not in the catalog") are extracted by
  regex, which is more precise than a model for this kind of literal detail.

Nothing here invents a value. A fact that was not stated stays ``None``.
"""

from __future__ import annotations

import re
from typing import Optional

from ..models import CATEGORY_BY_TOPIC, Entities, Topic, Understanding

# --------------------------------------------------------------------- safety
# Detected first and never overridden by the model (KB-09 is a hard rule).
SECURITY_PATTERNS = [
    r"phish\w*",
    r"malware",
    r"ransomware",
    r"\btrojan\b",
    r"spyware",
    r"\bvirus\b",
    r"suspicious (?:email|mail|message|link|attachment|activity|login|sign[- ]in)",
    r"(?:unauthori[sz]ed|unauthori[sz]ed) (?:access|login|sign[- ]in|attempt)",
    r"someone (?:accessed|logged into|is using) my",
    r"(?:account|laptop|machine) (?:was |has been )?(?:hacked|compromised)",
    r"security incident",
    r"scam (?:email|mail|message)",
    r"fake (?:email|invoice|login page)",
    r"asking for my (?:password|credentials|otp)",
]

PRIVILEGED_PATTERNS = [
    r"admin(?:istrator)? (?:access|right|privilege|account)",
    r"root access",
    r"sudo access",
    r"elevated (?:access|privilege|permission)",
    r"privileged access",
    r"domain admin",
]

# ------------------------------------------------------------ topic keywords
# (pattern, weight). Higher weight == stronger signal for that topic.
TOPIC_KEYWORDS: dict[Topic, list[tuple[str, float]]] = {
    Topic.GUEST_WIFI: [
        (r"guest wi[- ]?fi", 5), (r"visitor wi[- ]?fi", 5),
        (r"guest (?:network|internet|access|credential)", 4),
        (r"\bguest\b", 2.5), (r"front[- ]desk kiosk", 3),
    ],
    Topic.VPN_ACCESS: [(r"\bvpn\b", 5), (r"remote access tool", 2)],
    Topic.PASSWORD_RESET: [
        (r"password", 3), (r"locked out", 3.5), (r"account (?:is )?locked", 3.5),
        (r"reset my (?:password|credential)", 4), (r"unlock my account", 4),
        (r"self[- ]service portal", 2),
    ],
    Topic.LAPTOP_HARDWARE: [
        (r"laptop", 4), (r"\bnotebook\b", 3),
        (r"(?:machine|device|computer) (?:is )?(?:dead|won.?t turn on|not turning on)", 3),
        (r"screen (?:is )?flicker\w*", 3), (r"refresh cycle", 3),
        (r"hardware (?:failure|fault)", 3),
    ],
    Topic.SOFTWARE_INSTALL: [
        (r"install\w*", 3.5), (r"software", 3), (r"browser extension", 4),
        (r"\bextension\b", 2.5), (r"approved catalog", 4), (r"non[- ]catalog", 4),
        (r"\bcatalog\b", 3),
    ],
    Topic.PRINTER: [
        (r"printer", 5), (r"\bprint\w*\b", 2.5), (r"paper jam", 4),
        (r"print spooler", 4),
    ],
    Topic.MAILBOX_QUOTA: [
        (r"mailbox", 4.5), (r"\bquota\b", 4),
        (r"(?:mailbox|inbox|email) (?:is )?full", 4.5),
        (r"cannot send (?:email|mail)", 3), (r"archive (?:old )?mail", 3),
        (r"\b\d+\s?gb\b", 2),
    ],
    Topic.EXPENSE_SOFTWARE: [
        (r"expense", 5), (r"expense (?:tool|system|software|portal|management)", 6),
    ],
    Topic.WFH_EQUIPMENT: [
        (r"work(?:ing)? from home", 4), (r"\bwfh\b", 4), (r"home office", 4.5),
        (r"home desk", 4), (r"equipment allowance", 4.5), (r"\bmonitor\b", 3),
        (r"remotely \d+ days", 4), (r"\bremote\w*\b", 1.5),
    ],
}

# Words that mean the employee named *something* concrete. Used only to tell a
# vague message ("it's not working") apart from a specific but unsupported one.
CONCRETE_NOUNS = {
    "laptop", "computer", "pc", "desktop", "monitor", "screen", "printer",
    "email", "mailbox", "outlook", "vpn", "wifi", "wi-fi", "network",
    "internet", "password", "account", "login", "software", "application",
    "app", "browser", "extension", "server", "phone", "headset", "keyboard",
    "mouse", "dock", "docking", "camera", "webcam", "expense", "portal",
    "badge", "chair", "desk", "projector", "scanner", "database", "teams",
    "zoom", "drive", "folder", "file", "printer's", "charger", "battery",
}

URGENCY_PATTERNS = [
    r"\burgent\w*\b", r"\basap\b", r"immediately", r"\bcritical\b",
    r"blocking (?:my|our) work", r"cannot work", r"can.?t work",
    r"by (?:today|tomorrow)", r"\btomorrow\b", r"\btoday\b",
]

HARDWARE_FAILURE_PATTERNS = [
    r"(?:completely |totally )?dead", r"won.?t turn on", r"will not turn on",
    r"not turning on", r"won.?t power on", r"does(?:n.?t| not) power on",
    r"won.?t boot", r"not booting", r"no power", r"stopped working entirely",
]

HARDWARE_SYMPTOM_PATTERNS = [
    r"flicker\w*", r"overheat\w*", r"running slow\w*", r"battery drain\w*",
    r"fan (?:is )?loud", r"crack\w* screen", r"keyboard key",
]


def _search(patterns: list[str], text: str) -> Optional[str]:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(0)
    return None


def _score_topics(text: str) -> dict[Topic, float]:
    scores: dict[Topic, float] = {}
    for topic, patterns in TOPIC_KEYWORDS.items():
        total = 0.0
        for pattern, weight in patterns:
            if re.search(pattern, text, flags=re.IGNORECASE):
                total += weight
        if total:
            scores[topic] = total
    return scores


def extract_entities(text: str, topic: Topic) -> Entities:
    """Pull literal facts out of the employee's message."""
    low = text.lower()
    ent = Entities()

    # --- employee type
    if re.search(r"\bcontractor\b|\bcontract (?:worker|staff)\b", low):
        ent.employee_type = "contractor"
    elif re.search(r"full[- ]time|\bfte\b|permanent employee", low):
        ent.employee_type = "full_time"

    # --- account lockout / attempts
    attempts = re.search(r"(\d+)\s*(?:times|attempts|tries)", low)
    if attempts:
        ent.failed_attempts = int(attempts.group(1))
    if re.search(r"locked out|account (?:is )?locked|lock(?:ed)? me out", low):
        ent.account_locked_out = True
    elif ent.failed_attempts is not None and ent.failed_attempts >= 5:
        ent.account_locked_out = True

    # --- credential expiry
    if re.search(r"(?:credential|password|certificate)s? (?:have |has )?expired", low) or (
        re.search(r"\bexpired\b", low) and topic == Topic.VPN_ACCESS
    ):
        ent.credentials_expired = True

    # --- new access vs existing account
    if re.search(
        r"(?:need|want|request|get|grant|give) (?:me )?(?:\w+ ){0,3}?access|"
        r"access to the|set ?up (?:my )?(?:vpn|account)|do(?:es)? not have (?:vpn|access)|"
        r"don.?t have (?:vpn|access)|new (?:contractor|joiner|starter)",
        low,
    ):
        ent.new_access_request = True
    if re.search(
        r"already have (?:an |my )?(?:\w+ )?account|i have an account|existing account|"
        r"my (?:existing )?account (?:says|shows)",
        low,
    ):
        ent.existing_account = True
        ent.new_access_request = None if ent.new_access_request else ent.new_access_request

    # --- asset age (e.g. "3.5 years old", "2 years of service")
    age = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:\+\s*)?(?:year|yr)s?(?:\s*(?:old|of service|in service))?",
        low,
    )
    if age:
        ent.asset_age_years = float(age.group(1))

    # --- hardware condition
    failure = _search(HARDWARE_FAILURE_PATTERNS, low)
    symptom = _search(HARDWARE_SYMPTOM_PATTERNS, low)
    if failure:
        ent.reported_hardware_failure = True
        ent.hardware_symptom = failure
    elif symptom:
        ent.reported_hardware_failure = False
        ent.hardware_symptom = symptom

    if topic == Topic.LAPTOP_HARDWARE:
        ent.asset_type = "Laptop"

    # --- printer specifics
    tag = re.search(r"asset tag[:# ]*([a-z0-9\-]{3,})", low)
    if tag:
        ent.asset_tag = tag.group(1).upper()
    if re.search(
        r"already tried|tried restarting|restarted|still (?:not|shows|showing)|"
        r"keeps? (?:showing|happening)|persist\w*|no visible jam|does(?:n.?t| not) help",
        low,
    ):
        ent.already_tried_basic_steps = True

    # --- software catalog membership
    if re.search(r"not (?:in|part of) the (?:approved )?(?:software )?catalog|non[- ]catalog", low):
        ent.in_approved_catalog = False
    elif re.search(r"(?:in|from) the approved (?:software )?catalog|approved catalog software", low):
        ent.in_approved_catalog = True

    # --- mailbox
    if re.search(
        r"increase (?:my )?(?:mailbox|quota|storage)|quota increase|more (?:mailbox )?storage|"
        r"bigger mailbox|raise (?:my )?quota|increase beyond",
        low,
    ):
        ent.requests_quota_increase = True

    # --- remote working days
    days = re.search(r"(\d+)\s*\+?\s*days?\s*(?:a|per|each)\s*week", low)
    if days:
        ent.remote_days_per_week = int(days.group(1))
    elif re.search(r"more than 3 days", low):
        ent.remote_days_per_week = 4

    # --- security containment
    if re.search(r"forwarded|sent it (?:to|on)|shared it with|passed it (?:to|on)", low):
        ent.already_forwarded = True

    return ent


def classify_topic(text: str) -> tuple[Topic, bool]:
    """Return (topic, safety_override_applied).

    Security and privileged-access patterns win outright - that is the whole
    point of doing classification in code rather than leaving it to a model.
    """
    if _search(SECURITY_PATTERNS, text):
        return Topic.SECURITY_INCIDENT, True
    if _search(PRIVILEGED_PATTERNS, text):
        return Topic.PRIVILEGED_ACCESS, True

    scores = _score_topics(text)
    if not scores:
        return Topic.UNKNOWN, False
    best = max(scores.items(), key=lambda kv: kv[1])
    if best[1] < 2.5:
        return Topic.UNKNOWN, False
    return best[0], False


def is_vague(text: str, topic: Topic) -> bool:
    """True when the employee has not named any system, device or application."""
    if topic != Topic.UNKNOWN:
        return False
    words = re.findall(r"[a-zA-Z'\-]+", text.lower())
    has_noun = any(w in CONCRETE_NOUNS for w in words)
    return len(words) <= 14 and not has_noun


def describe_intent(topic: Topic, ent: Entities) -> str:
    """Short, human-readable intent label built from what was actually stated."""
    if topic == Topic.SECURITY_INCIDENT:
        return "Report of a suspected security incident"
    if topic == Topic.PRIVILEGED_ACCESS:
        return "Request for administrative / privileged access"
    if topic == Topic.GUEST_WIFI:
        return "Guest Wi-Fi access for a visitor"
    if topic == Topic.VPN_ACCESS:
        if ent.credentials_expired:
            return "VPN credential renewal after expiry"
        if ent.new_access_request:
            kind = ent.employee_type or "unspecified employee type"
            return f"New VPN access request ({kind.replace('_', '-')})"
        return "VPN connectivity issue"
    if topic == Topic.PASSWORD_RESET:
        return (
            "Account unlock after failed sign-in attempts"
            if ent.account_locked_out
            else "Password reset"
        )
    if topic == Topic.LAPTOP_HARDWARE:
        if ent.reported_hardware_failure:
            return "Laptop reported as failed - replacement enquiry"
        return "Laptop fault - repair or replacement enquiry"
    if topic == Topic.SOFTWARE_INSTALL:
        return "Software installation request"
    if topic == Topic.PRINTER:
        return "Printer troubleshooting"
    if topic == Topic.MAILBOX_QUOTA:
        return (
            "Mailbox quota increase request"
            if ent.requests_quota_increase
            else "Mailbox full - unable to send email"
        )
    if topic == Topic.EXPENSE_SOFTWARE:
        if ent.existing_account:
            return "Expense software sign-in problem on an existing account"
        return "Request for access to the expense software"
    if topic == Topic.WFH_EQUIPMENT:
        return "Home-office equipment enquiry"
    return "Unclear request - needs clarification"


def rule_based_understanding(text: str) -> Understanding:
    """Full deterministic Step 1."""
    topic, override = classify_topic(text)
    ent = extract_entities(text, topic)
    urgency = _search(URGENCY_PATTERNS, text)
    return Understanding(
        topic=topic,
        category=CATEGORY_BY_TOPIC[topic],
        intent=describe_intent(topic, ent),
        summary="",  # filled in by the responder / LLM
        entities=ent,
        urgency_stated=urgency,
        risk_level="high" if override else "low",
        classification_source="rules",
        is_vague=is_vague(text, topic),
    )


def safety_override_topic(text: str) -> Optional[Topic]:
    """Expose the hard override for the orchestrator to apply after the LLM."""
    topic, override = classify_topic(text)
    return topic if override else None
