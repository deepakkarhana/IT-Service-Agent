"""Structured types used across the agent pipeline.

Every stage of the pipeline exchanges validated Pydantic objects rather than
free text. That is what makes the agent auditable: each field can be traced to
either the supplied data pack or a deterministic rule.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class Topic(str, Enum):
    """Closed set of issue types the agent is allowed to recognise.

    The set is closed on purpose: it maps 1:1 onto the supplied knowledge base
    (plus two "no supporting policy" buckets). An LLM cannot invent a new topic
    and therefore cannot invent a new policy path.
    """

    PASSWORD_RESET = "password_reset"
    VPN_ACCESS = "vpn_access"
    LAPTOP_HARDWARE = "laptop_hardware"
    SOFTWARE_INSTALL = "software_install"
    PRINTER = "printer"
    MAILBOX_QUOTA = "mailbox_quota"
    GUEST_WIFI = "guest_wifi"
    EXPENSE_SOFTWARE = "expense_software"
    SECURITY_INCIDENT = "security_incident"
    WFH_EQUIPMENT = "wfh_equipment"
    PRIVILEGED_ACCESS = "privileged_access"
    UNKNOWN = "unknown"


class Decision(str, Enum):
    RESOLVE = "RESOLVE"
    CLARIFY = "CLARIFY"
    ESCALATE = "ESCALATE"
    ROUTE_TO_OTHER_FUNCTION = "ROUTE_TO_OTHER_FUNCTION"
    CREATE_TICKET = "CREATE_TICKET"


RiskLevel = Literal["low", "medium", "high"]
PriorityLevel = Literal["LOW", "MEDIUM", "HIGH"]

CATEGORY_BY_TOPIC: dict[Topic, str] = {
    Topic.PASSWORD_RESET: "Account Access",
    Topic.VPN_ACCESS: "Network Access",
    Topic.LAPTOP_HARDWARE: "Hardware",
    Topic.SOFTWARE_INSTALL: "Software",
    Topic.PRINTER: "Hardware",
    Topic.MAILBOX_QUOTA: "Email",
    Topic.GUEST_WIFI: "Network Access",
    Topic.EXPENSE_SOFTWARE: "Business Applications",
    Topic.SECURITY_INCIDENT: "Security",
    Topic.WFH_EQUIPMENT: "Hardware",
    Topic.PRIVILEGED_ACCESS: "Account Access",
    Topic.UNKNOWN: "Unclassified",
}


class Entities(BaseModel):
    """Facts extracted from the employee's own words.

    Every field defaults to ``None`` which means "not stated". The agent never
    fills a ``None`` with a guess: it either asks, or it explains the policy for
    the situations it can already distinguish.
    """

    employee_type: Optional[Literal["full_time", "contractor"]] = None
    account_locked_out: Optional[bool] = None
    failed_attempts: Optional[int] = None
    credentials_expired: Optional[bool] = None
    new_access_request: Optional[bool] = None
    existing_account: Optional[bool] = None
    asset_type: Optional[str] = None
    asset_age_years: Optional[float] = None
    # True  -> the employee reports a total failure (e.g. will not power on)
    # False -> a symptom that is not by itself a confirmed failure
    # None  -> nothing stated
    reported_hardware_failure: Optional[bool] = None
    hardware_symptom: Optional[str] = None
    asset_tag: Optional[str] = None
    already_tried_basic_steps: Optional[bool] = None
    software_name: Optional[str] = None
    in_approved_catalog: Optional[bool] = None
    requests_quota_increase: Optional[bool] = None
    remote_days_per_week: Optional[int] = None
    already_forwarded: Optional[bool] = None

    def merged_with(self, other: "Entities") -> "Entities":
        """Return a copy where this object's stated values win over ``other``.

        Used to merge deterministic regex extraction (high precision, wins) with
        LLM extraction (better at paraphrase, used to fill the gaps).
        """
        merged = self.model_dump()
        for key, value in other.model_dump().items():
            if merged.get(key) is None and value is not None:
                merged[key] = value
        return Entities(**merged)


class Understanding(BaseModel):
    """Step 1 output."""

    topic: Topic = Topic.UNKNOWN
    category: str = "Unclassified"
    intent: str = ""
    summary: str = ""
    entities: Entities = Field(default_factory=Entities)
    urgency_stated: Optional[str] = None
    missing_information: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = "low"
    classification_source: Literal["rules", "llm", "llm+safety-override"] = "rules"
    is_vague: bool = False


class LLMUnderstanding(BaseModel):
    """Schema the LLM must return. Anything else is rejected and ignored."""

    topic: Topic
    intent: str = ""
    summary: str = ""
    urgency_stated: Optional[str] = None
    entities: Entities = Field(default_factory=Entities)


class SourceRef(BaseModel):
    """A knowledge-base citation shown to the employee."""

    id: str
    title: str
    category: str
    excerpt: str
    relevance: Literal["authoritative", "supporting"] = "supporting"
    match_score: float = 0.0


class PolicyPoint(BaseModel):
    """A single policy statement, copied verbatim from the knowledge base."""

    source_id: str
    text: str


class RelatedTicket(BaseModel):
    ticket_id: str
    issue_summary: str
    status: str
    active: bool
    note: str = ""


class PolicyConflict(BaseModel):
    detected: bool = False
    summary: str = ""
    positions: list[PolicyPoint] = Field(default_factory=list)
    resolution_path: str = ""


class Ticket(BaseModel):
    ticket_id: str
    employee: str
    issue_summary: str
    issue_detail: str = ""
    category: str
    priority: PriorityLevel
    decision: Decision
    next_action: str
    status: str
    assigned_team: str
    source_policy: list[str] = Field(default_factory=list)
    created_at: str
    active: bool = True
    origin: Literal["data_pack", "prototype_generated"] = "prototype_generated"
    source_request_id: Optional[str] = None


class AuditEvent(BaseModel):
    timestamp: str
    interaction_id: str
    request_id: Optional[str] = None
    employee: str
    stage: str
    detail: str
    data: dict[str, Any] = Field(default_factory=dict)


class AgentResponseText(BaseModel):
    """Step 5 output: the four things the employee is told."""

    understood: str
    policy_says: list[PolicyPoint] = Field(default_factory=list)
    what_happens_next: str = ""
    your_actions: list[str] = Field(default_factory=list)
    notice: Optional[str] = None


class AgentResult(BaseModel):
    """The single structured object the API returns and the UI renders."""

    interaction_id: str
    request_id: Optional[str] = None
    employee: str
    employee_input: str
    created_at: str
    mode: Literal["llm", "fallback"]
    mode_detail: str

    understanding: Understanding
    decision: Decision
    decision_reason: str
    risk_level: RiskLevel
    priority: PriorityLevel
    assigned_team: str
    next_action: str
    clarifying_question: Optional[str] = None
    policy_conflict: Optional[PolicyConflict] = None

    response: AgentResponseText
    sources: list[SourceRef] = Field(default_factory=list)
    related_tickets: list[RelatedTicket] = Field(default_factory=list)

    ticket_required: bool = False
    ticket: Optional[Ticket] = None
    audit_events: list[AuditEvent] = Field(default_factory=list)


class AgentRequestIn(BaseModel):
    """API input."""

    message: str = Field(min_length=1, max_length=4000)
    employee: str = "Employee (demo user)"
    request_id: Optional[str] = None
    persist: bool = True
