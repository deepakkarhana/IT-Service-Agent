"""FastAPI application.

Thin HTTP layer: it validates input, calls the agent, and returns the single
structured result object the UI renders. No business logic lives here.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .agent.orchestrator import get_agent
from .config import settings
from .data_store import get_store
from .models import AgentRequestIn, AgentResult

app = FastAPI(
    title="IT Service Agent API",
    description="Internal IT service agent: understand, retrieve, decide, ticket, audit.",
    version="1.0.0",
)

# The Vite dev server runs on a different port, so the browser needs CORS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Sample requests for the demo buttons. Each one exercises a different branch of
# the decision engine.
DEMO_SAMPLES = [
    {"label": "Guest Wi-Fi", "hint": "Direct resolution",
     "text": "Can I get Wi-Fi access for a guest visiting tomorrow?"},
    {"label": "Phishing incident", "hint": "Security escalation",
     "text": "I think I received a phishing email asking for my password, and I already forwarded it to my teammates to warn them."},
    {"label": "VPN expired", "hint": "Direct resolution",
     "text": "My VPN stopped working. It says my credentials expired."},
    {"label": "Contractor VPN", "hint": "Routed for approval",
     "text": "I'm a contractor and I need VPN access to start work."},
    {"label": "Expense access", "hint": "Cross-department routing",
     "text": "I need access to the expense management system."},
    {"label": "Expense login", "hint": "Stays with IT",
     "text": "I already have an expense account but I can't log in. It says invalid credentials."},
    {"label": "Laptop replacement", "hint": "Policy conflict",
     "text": "My laptop is 3.5 years old and completely dead. Can I get a replacement?"},
    {"label": "Laptop flickering", "hint": "Verify before escalating",
     "text": "My laptop screen is flickering and it is 2 years old. Do I need a repair or a replacement?"},
    {"label": "Vague request", "hint": "Clarifying question",
     "text": "hey can you help, its not working"},
    {"label": "Admin access", "hint": "No policy - escalate",
     "text": "I need admin access to the finance reporting server."},
]

CAPABILITIES = [
    {"title": "Understand", "detail": "Extracts the issue, the facts stated and what is missing - without guessing."},
    {"title": "Retrieve", "detail": "Searches the IT knowledge base and the ticket queue, and shows the source used."},
    {"title": "Decide", "detail": "Resolve, clarify, route, escalate or raise a ticket - one explicit decision."},
    {"title": "Escalate", "detail": "Security incidents and unsupported requests always go to a human."},
    {"title": "Audit", "detail": "Every stage of every interaction is timestamped and recorded."},
]


@app.get("/api/health")
def health() -> dict[str, Any]:
    """Tells the UI whether it is running in LLM mode or fallback mode."""
    return {
        "status": "ok",
        "mode": "llm" if settings.llm_enabled else "fallback",
        "model": settings.llm_model if settings.llm_enabled else None,
        "mode_detail": (
            f"LLM mode is configured ({settings.llm_model}). If a call fails, the agent "
            "falls back to deterministic rules automatically."
            if settings.llm_enabled
            else "Demo / fallback mode: no LLM_API_KEY is set, so understanding runs on "
            "deterministic rules. Decisions, policy text and audit are deterministic in "
            "both modes."
        ),
    }


@app.get("/api/capabilities")
def capabilities() -> list[dict[str, str]]:
    return CAPABILITIES


@app.get("/api/demo-samples")
def demo_samples() -> list[dict[str, str]]:
    return DEMO_SAMPLES


@app.post("/api/agent/handle", response_model=AgentResult)
def handle_request(payload: AgentRequestIn) -> AgentResult:
    store = get_store()
    agent = get_agent(store)
    try:
        return agent.handle(
            message=payload.message,
            employee=payload.employee,
            request_id=payload.request_id,
            persist=payload.persist,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # the UI must never see a bare 500
        raise HTTPException(
            status_code=500,
            detail=f"The agent could not process this request ({type(exc).__name__}).",
        ) from exc


@app.get("/api/knowledge-base")
def knowledge_base() -> dict[str, Any]:
    store = get_store()
    return {"policies": store.policies}


@app.get("/api/requests")
def list_requests() -> dict[str, Any]:
    """Queue view.

    Each row carries a deterministic, rules-only preview of what the agent would
    decide. It is computed without calling the LLM and without persisting
    anything, so opening the queue is instant and costs nothing.
    """
    store = get_store()
    agent = get_agent(store)
    rows = []
    for req in store.requests:
        preview = agent.handle(
            message=req["request"],
            employee=req["employee"],
            request_id=req["request_id"],
            persist=False,
            use_llm=False,
        )
        rows.append(
            {
                **req,
                "preview": {
                    "topic": preview.understanding.topic.value,
                    "category": preview.understanding.category,
                    "intent": preview.understanding.intent,
                    "decision": preview.decision.value,
                    "priority": preview.priority,
                    "assigned_team": preview.assigned_team,
                    "sources": [s.id for s in preview.sources],
                    "conflict": bool(
                        preview.policy_conflict and preview.policy_conflict.detected
                    ),
                },
            }
        )
    return {"requests": rows}


@app.post("/api/requests/{request_id}/triage", response_model=AgentResult)
def triage_request(request_id: str) -> AgentResult:
    """Run the full pipeline on a queued request and record the result."""
    store = get_store()
    req = store.request(request_id)
    if req is None:
        raise HTTPException(status_code=404, detail=f"Unknown request id {request_id}")
    agent = get_agent(store)
    try:
        return agent.handle(
            message=req["request"],
            employee=req["employee"],
            request_id=request_id,
            persist=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/tickets")
def list_tickets() -> dict[str, Any]:
    store = get_store()
    tickets = store.all_tickets()
    return {
        "active": [t for t in tickets if t.get("active")],
        "closed": [t for t in tickets if not t.get("active")],
    }


@app.get("/api/audit")
def audit_trail(limit: int = 200) -> dict[str, Any]:
    store = get_store()
    events = [e.model_dump() for e in store.audit_log][-limit:]
    return {"events": list(reversed(events)), "total": len(store.audit_log)}


@app.post("/api/runtime/reset")
def reset_runtime() -> dict[str, str]:
    """Clear prototype-generated tickets and audit events (demo convenience)."""
    get_store().reset_runtime()
    return {"status": "cleared"}
