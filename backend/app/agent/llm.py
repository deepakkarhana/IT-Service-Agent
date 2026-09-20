"""Optional LLM layer.

The LLM is deliberately given the *smallest useful job*: read the employee's
message and return structured facts (topic + entities + a one-line summary).
It never decides, never writes policy text and never chooses a team. Those come
from :mod:`policy_engine`, which is plain Python.

If no API key is set, the request times out, the endpoint errors, or the model
returns anything that fails validation, this module returns ``None`` and the
pipeline continues on the deterministic rules. The UI stays fully functional.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Optional

import httpx
from pydantic import ValidationError

from ..config import settings
from ..models import LLMUnderstanding, Topic

MAX_SUMMARY_CHARS = 280

SYSTEM_PROMPT = """You are the information-extraction component of an internal IT service desk agent.

You do NOT answer the employee, you do NOT give advice, and you do NOT state or
invent any company policy. You only read the message and return structured facts.

Return ONLY a JSON object with these keys:
  "topic": one of {topics}
  "intent": short label, max 12 words, describing what the employee wants
  "summary": one plain sentence restating the employee's issue in your own words.
             Do not add any policy, rule, cause or solution.
  "urgency_stated": the employee's own urgency words, or null if they stated none
  "entities": object with any of these keys that the message actually states:
      employee_type: "full_time" | "contractor" | null
      account_locked_out: true | false | null
      failed_attempts: integer | null
      credentials_expired: true | false | null
      new_access_request: true | false | null
      existing_account: true | false | null
      asset_type: string | null
      asset_age_years: number | null
      reported_hardware_failure: true if the employee reports the device does not
          work at all, false if they report a lesser symptom, null if not stated
      hardware_symptom: string | null
      asset_tag: string | null
      already_tried_basic_steps: true | false | null
      software_name: string | null
      in_approved_catalog: true | false | null
      requests_quota_increase: true | false | null
      remote_days_per_week: integer | null
      already_forwarded: true | false | null

Rules:
- Use null for anything the employee did not state. Never guess a value.
- "topic" must be exactly one of the listed values. Use "unknown" if none fit.
- Output raw JSON only, no markdown fences and no commentary."""


@dataclass
class LLMOutcome:
    understanding: Optional[LLMUnderstanding]
    ok: bool
    detail: str


def _sanitize_summary(text: str) -> str:
    clean = re.sub(r"\s+", " ", (text or "")).strip()
    return clean[:MAX_SUMMARY_CHARS]


def _extract_json(raw: str) -> dict:
    """Tolerate a model that wraps its JSON in prose or code fences."""
    raw = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", raw, flags=re.DOTALL)
    if fence:
        raw = fence.group(1).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(raw[start : end + 1])


def extract_understanding(message: str) -> LLMOutcome:
    """Call the configured LLM. Any failure is reported, never raised."""
    if not settings.llm_enabled:
        return LLMOutcome(None, False, "No LLM_API_KEY configured - running on rules.")

    topics = ", ".join(f'"{t.value}"' for t in Topic)
    payload = {
        "model": settings.llm_model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT.format(topics=topics)},
            {"role": "user", "content": message},
        ],
    }
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
            resp = client.post(
                f"{settings.llm_base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
        if resp.status_code != 200:
            return LLMOutcome(
                None, False, f"LLM HTTP {resp.status_code} - fell back to rules."
            )
        content = resp.json()["choices"][0]["message"]["content"]
    except httpx.TimeoutException:
        return LLMOutcome(None, False, "LLM request timed out - fell back to rules.")
    except Exception as exc:  # network error, bad envelope, missing key in JSON
        return LLMOutcome(
            None, False, f"LLM call failed ({type(exc).__name__}) - fell back to rules."
        )

    try:
        data = _extract_json(content)
    except Exception:
        return LLMOutcome(
            None, False, "LLM returned malformed JSON - fell back to rules."
        )

    if isinstance(data.get("entities"), dict):
        # Drop any key the model invented so validation cannot fail on it.
        allowed = set(LLMUnderstanding.model_fields["entities"].annotation.model_fields)
        data["entities"] = {k: v for k, v in data["entities"].items() if k in allowed}

    try:
        understanding = LLMUnderstanding(**data)
    except ValidationError as exc:
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(p) for p in first.get("loc", ())) or "payload"
        return LLMOutcome(
            None, False, f"LLM output failed validation on '{field}' - fell back to rules."
        )

    understanding.summary = _sanitize_summary(understanding.summary)
    understanding.intent = _sanitize_summary(understanding.intent)[:120]
    return LLMOutcome(understanding, True, f"LLM mode ({settings.llm_model}).")
