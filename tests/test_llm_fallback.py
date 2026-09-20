"""The application must never break because of the LLM.

These tests simulate every way the LLM layer can fail and assert that the agent
still returns a complete, correctly decided result in fallback mode.
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.app.agent import llm as llm_module  # noqa: E402
from backend.app.agent.orchestrator import ITServiceAgent  # noqa: E402
from backend.app.data_store import DataStore  # noqa: E402
from backend.app.models import Decision, Topic  # noqa: E402


@pytest.fixture(scope="module")
def agent() -> ITServiceAgent:
    return ITServiceAgent(DataStore())


class _FakeResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def _patch_post(monkeypatch, behaviour):
    """Replace httpx.Client.post with a stub, and pretend a key is configured."""
    monkeypatch.setattr(llm_module.settings, "llm_api_key", "test-key", raising=False)
    monkeypatch.setattr(llm_module.settings, "llm_model", "test-model", raising=False)
    monkeypatch.setattr(httpx.Client, "post", behaviour, raising=False)


def _content(text: str):
    return {"choices": [{"message": {"content": text}}]}


def test_no_api_key_reports_fallback_mode(monkeypatch):
    monkeypatch.setattr(llm_module.settings, "llm_api_key", "", raising=False)
    outcome = llm_module.extract_understanding("My VPN credentials expired.")
    assert outcome.ok is False
    assert outcome.understanding is None
    assert "No LLM_API_KEY" in outcome.detail


def test_timeout_falls_back_without_raising(monkeypatch, agent):
    def boom(self, *args, **kwargs):
        raise httpx.TimeoutException("too slow")

    _patch_post(monkeypatch, boom)
    result = agent.handle(
        "Can I get Wi-Fi access for a guest visiting tomorrow?", persist=False
    )
    assert result.mode == "fallback"
    assert "timed out" in result.mode_detail
    assert result.decision == Decision.RESOLVE
    assert [s.id for s in result.sources] == ["KB-07"]


def test_http_error_falls_back(monkeypatch, agent):
    _patch_post(monkeypatch, lambda self, *a, **k: _FakeResponse(401, {}))
    result = agent.handle("My VPN credentials expired.", persist=False)
    assert result.mode == "fallback"
    assert "401" in result.mode_detail
    assert result.decision == Decision.RESOLVE


def test_network_error_falls_back(monkeypatch, agent):
    def boom(self, *args, **kwargs):
        raise httpx.ConnectError("no route to host")

    _patch_post(monkeypatch, boom)
    result = agent.handle("My printer is not printing.", persist=False)
    assert result.mode == "fallback"
    assert result.decision == Decision.RESOLVE


def test_malformed_json_falls_back(monkeypatch, agent):
    _patch_post(
        monkeypatch,
        lambda self, *a, **k: _FakeResponse(200, _content("I'm sorry, I cannot do that.")),
    )
    result = agent.handle("My mailbox is full.", persist=False)
    assert result.mode == "fallback"
    assert "malformed JSON" in result.mode_detail
    assert result.decision == Decision.RESOLVE


def test_invalid_topic_is_rejected_by_validation(monkeypatch, agent):
    _patch_post(
        monkeypatch,
        lambda self, *a, **k: _FakeResponse(
            200, _content('{"topic": "order_a_new_chair", "summary": "x"}')
        ),
    )
    result = agent.handle("My mailbox is full.", persist=False)
    assert result.mode == "fallback"
    assert "validation" in result.mode_detail
    assert result.decision == Decision.RESOLVE


def test_json_wrapped_in_code_fences_is_still_accepted(monkeypatch, agent):
    payload = (
        '```json\n{"topic": "guest_wifi", "intent": "guest wifi", '
        '"summary": "A visitor needs Wi-Fi tomorrow.", "entities": {}}\n```'
    )
    _patch_post(monkeypatch, lambda self, *a, **k: _FakeResponse(200, _content(payload)))
    result = agent.handle("A guest needs wifi tomorrow", persist=False)
    assert result.mode == "llm"
    assert result.understanding.topic == Topic.GUEST_WIFI
    assert result.response.understood == "A visitor needs Wi-Fi tomorrow."


def test_invented_entity_keys_are_dropped_not_fatal(monkeypatch, agent):
    payload = (
        '{"topic": "guest_wifi", "intent": "guest wifi", "summary": "Visitor Wi-Fi.", '
        '"entities": {"employee_type": "contractor", "approval_level": "director", '
        '"budget_code": "X-12"}}'
    )
    _patch_post(monkeypatch, lambda self, *a, **k: _FakeResponse(200, _content(payload)))
    result = agent.handle("A guest needs wifi tomorrow", persist=False)
    assert result.mode == "llm"
    assert result.understanding.entities.employee_type == "contractor"
    assert not hasattr(result.understanding.entities, "budget_code")


def test_model_cannot_reclassify_a_security_incident(monkeypatch, agent):
    """The safety override is the whole reason classification is not left to the LLM."""
    payload = (
        '{"topic": "password_reset", "intent": "password help", '
        '"summary": "Employee needs password help.", "entities": {}}'
    )
    _patch_post(monkeypatch, lambda self, *a, **k: _FakeResponse(200, _content(payload)))
    result = agent.handle(
        "I received a phishing email asking for my password.", persist=False
    )
    assert result.understanding.topic == Topic.SECURITY_INCIDENT
    assert result.understanding.classification_source == "llm+safety-override"
    assert result.decision == Decision.ESCALATE
    assert result.assigned_team == "Security Team"
    assert any(e.stage == "safety_override" for e in result.audit_events)


def test_regex_facts_win_over_a_contradicting_model(monkeypatch, agent):
    payload = (
        '{"topic": "laptop_hardware", "intent": "replacement", '
        '"summary": "Laptop replacement request.", '
        '"entities": {"asset_age_years": 9, "reported_hardware_failure": false}}'
    )
    _patch_post(monkeypatch, lambda self, *a, **k: _FakeResponse(200, _content(payload)))
    result = agent.handle(
        "My laptop is 3.5 years old and completely dead. Can I get a replacement?",
        persist=False,
    )
    # The message says 3.5 years and "completely dead"; the model said 9 and false.
    assert result.understanding.entities.asset_age_years == 3.5
    assert result.understanding.entities.reported_hardware_failure is True
    assert result.policy_conflict.detected is True


def test_an_overlong_model_summary_is_truncated(monkeypatch, agent):
    payload = (
        '{"topic": "guest_wifi", "intent": "guest wifi", "summary": "'
        + ("word " * 200).strip()
        + '", "entities": {}}'
    )
    _patch_post(monkeypatch, lambda self, *a, **k: _FakeResponse(200, _content(payload)))
    result = agent.handle("A guest needs wifi", persist=False)
    assert len(result.response.understood) <= llm_module.MAX_SUMMARY_CHARS


def test_policy_text_is_never_taken_from_the_model(monkeypatch, agent):
    """Even a model that tries to state policy cannot change the cited text."""
    payload = (
        '{"topic": "guest_wifi", "intent": "guest wifi", '
        '"summary": "Guest Wi-Fi is valid for 30 days and requires a director sign-off.", '
        '"entities": {}}'
    )
    _patch_post(monkeypatch, lambda self, *a, **k: _FakeResponse(200, _content(payload)))
    result = agent.handle("A guest needs wifi tomorrow", persist=False)
    store = agent.store
    for point in result.response.policy_says:
        assert point.text in store.policy(point.source_id)["key_points"]
    assert all("30 days" not in point.text for point in result.response.policy_says)
