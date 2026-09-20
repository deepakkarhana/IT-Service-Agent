"""Retrieval over the supplied knowledge base and ticket queue.

Two things happen here, and keeping them separate is deliberate:

1. **Lexical search** (a small BM25 implementation, no external services) scores
   every policy against the employee's wording. This is what makes retrieval
   feel like search and is what produces the "match score" in the UI.
2. **Topic pinning** guarantees that the policy which actually governs the
   detected topic is always retrieved, even if the employee used words that do
   not appear in the policy text. Search alone is not reliable enough to decide
   company policy on.

The result is a list of citations the UI shows, every one of them an ID that
exists in ``data/knowledge_base.json``.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Iterable

from .data_store import DataStore
from .models import RelatedTicket, SourceRef, Topic

# Policies that govern each topic. Empty list == the data pack has no policy
# covering this topic, which the decision engine treats as "cannot answer".
TOPIC_SOURCES: dict[Topic, list[str]] = {
    Topic.PASSWORD_RESET: ["KB-01"],
    Topic.VPN_ACCESS: ["KB-02"],
    Topic.LAPTOP_HARDWARE: ["KB-03", "ASSET-POL"],
    Topic.SOFTWARE_INSTALL: ["KB-04"],
    Topic.PRINTER: ["KB-05"],
    Topic.MAILBOX_QUOTA: ["KB-06"],
    Topic.GUEST_WIFI: ["KB-07"],
    Topic.EXPENSE_SOFTWARE: ["KB-08"],
    Topic.SECURITY_INCIDENT: ["KB-09"],
    Topic.WFH_EQUIPMENT: ["KB-10"],
    Topic.PRIVILEGED_ACCESS: [],
    Topic.UNKNOWN: [],
}

# Keywords used to pull historical / active tickets as context for a topic.
TOPIC_TICKET_KEYWORDS: dict[Topic, list[str]] = {
    Topic.PASSWORD_RESET: ["password"],
    Topic.VPN_ACCESS: ["vpn"],
    Topic.LAPTOP_HARDWARE: ["laptop"],
    Topic.SOFTWARE_INSTALL: ["software"],
    Topic.PRINTER: ["printer"],
    Topic.MAILBOX_QUOTA: ["mailbox"],
    Topic.GUEST_WIFI: ["guest wi-fi"],
    Topic.EXPENSE_SOFTWARE: [],
    Topic.SECURITY_INCIDENT: ["phishing"],
    Topic.WFH_EQUIPMENT: ["home office"],
    Topic.PRIVILEGED_ACCESS: ["admin access"],
    Topic.UNKNOWN: [],
}

STOPWORDS = {
    "a", "about", "am", "an", "and", "any", "are", "as", "at", "be", "been",
    "but", "by", "can", "cannot", "do", "does", "for", "from", "get", "has",
    "have", "hey", "how", "i", "if", "in", "into", "is", "it", "its", "just",
    "me", "my", "need", "no", "not", "now", "of", "on", "or", "please", "so",
    "that", "the", "there", "this", "to", "up", "want", "was", "we", "what",
    "when", "will", "with", "would", "you", "your",
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Lowercase, split, drop stopwords, and do a crude plural trim."""
    tokens = []
    for raw in _TOKEN_RE.findall(text.lower()):
        if raw in STOPWORDS or len(raw) < 2:
            continue
        if len(raw) > 4 and raw.endswith("s") and not raw.endswith("ss"):
            raw = raw[:-1]
        tokens.append(raw)
    return tokens


class PolicyRetriever:
    """BM25 over the 11 supplied policies. Small data, so this stays in memory."""

    K1 = 1.5
    B = 0.75
    # A supporting source must clear both gates: an absolute floor, and 70% of
    # the best score for this query. Common words like "access", "password" or
    # "account" appear in several policies and would otherwise attach irrelevant
    # citations to an otherwise clean answer.
    MIN_SCORE = 3.5
    MIN_SCORE_RATIO = 0.7

    def __init__(self, store: DataStore):
        self.store = store
        self._docs: dict[str, list[str]] = {}
        for policy in store.policies:
            blob = " ".join(
                [policy["title"], policy["category"], policy["content"]]
                + policy.get("key_points", [])
            )
            self._docs[policy["id"]] = tokenize(blob)

        self._freqs = {pid: Counter(toks) for pid, toks in self._docs.items()}
        self._lengths = {pid: len(toks) for pid, toks in self._docs.items()}
        self._avg_len = (
            sum(self._lengths.values()) / len(self._lengths) if self._lengths else 0.0
        )
        n_docs = len(self._docs)
        doc_freq: Counter[str] = Counter()
        for toks in self._docs.values():
            doc_freq.update(set(toks))
        self._idf = {
            term: math.log(1 + (n_docs - df + 0.5) / (df + 0.5))
            for term, df in doc_freq.items()
        }

    def score_all(self, query: str) -> list[tuple[str, float]]:
        query_terms = tokenize(query)
        scored: list[tuple[str, float]] = []
        for pid, freqs in self._freqs.items():
            score = 0.0
            length = self._lengths[pid] or 1
            for term in query_terms:
                tf = freqs.get(term, 0)
                if not tf:
                    continue
                idf = self._idf.get(term, 0.0)
                denom = tf + self.K1 * (
                    1 - self.B + self.B * length / (self._avg_len or 1)
                )
                score += idf * (tf * (self.K1 + 1)) / denom
            if score > 0:
                scored.append((pid, round(score, 3)))
        return sorted(scored, key=lambda x: x[1], reverse=True)

    def retrieve(self, query: str, topic: Topic, limit: int = 4) -> list[SourceRef]:
        """Pinned authoritative policies first, then strong lexical matches.

        When a topic has no governing policy (privileged access, unknown), this
        returns an empty list on purpose. Showing a weak keyword match there
        would imply the request is covered by a policy when it is not.
        """
        lexical = dict(self.score_all(query))
        pinned = TOPIC_SOURCES.get(topic, [])
        if not pinned:
            return []
        refs: list[SourceRef] = []

        for pid in pinned:
            refs.append(self._to_ref(pid, lexical.get(pid, 0.0), "authoritative"))

        top_score = max(lexical.values(), default=0.0)
        cutoff = max(self.MIN_SCORE, self.MIN_SCORE_RATIO * top_score)
        for pid, score in sorted(lexical.items(), key=lambda x: x[1], reverse=True):
            if len(refs) >= limit:
                break
            if pid in pinned or score < cutoff:
                continue
            refs.append(self._to_ref(pid, score, "supporting"))
        return refs

    def _to_ref(self, policy_id: str, score: float, relevance: str) -> SourceRef:
        policy = self.store.policy(policy_id)
        return SourceRef(
            id=policy_id,
            title=policy["title"],
            category=policy["category"],
            excerpt=policy["content"],
            relevance=relevance,  # type: ignore[arg-type]
            match_score=score,
        )


def retrieve_related_tickets(
    store: DataStore, topic: Topic, limit: int = 3
) -> list[RelatedTicket]:
    """Pull ticket context for a topic.

    Closed tickets are labelled as history/precedent so neither the agent nor
    the person reading the screen mistakes a past outcome for current policy.
    """
    keywords = TOPIC_TICKET_KEYWORDS.get(topic, [])
    if not keywords:
        return []

    policy_ids = set(TOPIC_SOURCES.get(topic, []))
    matches: list[RelatedTicket] = []
    for ticket in store.all_tickets():
        summary = ticket["issue_summary"].lower()
        keyword_hit = any(k in summary for k in keywords)
        policy_hit = bool(policy_ids & set(ticket.get("related_policy") or []))
        if not (keyword_hit or policy_hit):
            continue
        active = bool(ticket.get("active"))
        matches.append(
            RelatedTicket(
                ticket_id=ticket["ticket_id"],
                issue_summary=ticket["issue_summary"],
                status=ticket["status"],
                active=active,
                note=(
                    "Active case - still requires action"
                    if active
                    else "Closed ticket - history and precedent only, not policy"
                ),
            )
        )
    # Active cases first, they are the ones that may need action.
    matches.sort(key=lambda t: (not t.active, t.ticket_id))
    return matches[:limit]
