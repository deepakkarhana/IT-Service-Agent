# Interview / defence questions

Likely questions with concise, technically accurate answers. Every answer
describes what the project **actually does** — nothing here overstates it.

---

### 1. Why is this an agent and not a chatbot?

A chatbot produces a reply. This produces a **decision and an action**.

For every request it picks exactly one of five decisions (RESOLVE, CLARIFY,
ROUTE_TO_OTHER_FUNCTION, ESCALATE, CREATE_TICKET), and that decision changes
state in the system — it creates a structured ticket, raises an escalation to a
named team, or deliberately creates nothing and asks a question instead. It also
decides whether it has enough information to act at all.

The output is a structured object, not a paragraph. The paragraph is just how we
render it.

### 2. Why did you use an LLM at all?

For the one thing it is genuinely better at than code: reading a message written
in someone's own words and turning it into structured facts. People write
"my machine's about three and a half years old and it won't come on" — a model
handles that paraphrasing well.

But that is *all* it does. It returns a topic from a fixed list, an intent
label, a one-line summary, and the facts stated. It never decides, never picks a
team, never writes policy text.

And the project is fully usable without it — the fallback classifier handles all
the demo cases.

### 3. Where is deterministic logic used, and why there?

Everything that must be identical every time:

- **The decision** (`policy_engine.py`) — same input, same decision, always.
- **Security escalation** — fixed patterns in code, matched before anything else.
- **Policy text shown to the employee** — copied verbatim from the knowledge
  base JSON via `store.policy_point()`.
- **Routing** — which team owns what is a business rule, not a language task.
- **Ticket structure and the audit trail** — records must be structurally
  identical every time.
- **Literal fact extraction** — "3.5 years", "6 times", "contractor" come from
  regex, which beats a model on that kind of detail.

The rule: *the model understands, code decides.*

### 4. How does retrieval work?

Two mechanisms:

1. **BM25 lexical search** over the 11 policies, implemented in about 40 lines
   of Python — term frequency saturation, inverse document frequency, document
   length normalisation. It produces the match score shown in the UI.
2. **Topic pinning** — a map from topic to the policy IDs that govern it, so the
   right policy is always retrieved even if the employee's wording shares no
   words with it.

A non-pinned "supporting" source is only shown if it clears an absolute score
floor *and* 70% of the best score for that query. Without that gate, common
words like "access" or "password" attached irrelevant citations to clean
answers — that was a real bug I found and fixed.

If the topic has no governing policy, retrieval returns nothing on purpose.

### 5. How do you prevent hallucination?

Four layers:

1. **The model cannot write policy.** The "what the policy says" section is
   assembled from key points copied verbatim out of `knowledge_base.json`. There
   is a test asserting every displayed sentence appears verbatim in the source.
2. **Closed taxonomy.** The model must return one of 12 topics. Anything else
   fails Pydantic validation and the whole result is discarded.
3. **Safety override.** Security and privileged-access patterns are matched in
   code and overrule the model. Tested with a stub model that deliberately
   misclassifies a phishing report.
4. **No-match means no answer.** If nothing covers the request, the agent says
   it does not have enough information and escalates.

### 6. What happens when no policy matches?

It distinguishes two cases:

- **Nothing concrete was named** ("it's not working") → `CLARIFY`, and it asks
  which system and what error. No sources shown, no ticket created, and it does
  not guess a topic.
- **Something was named but no policy covers it** (a broken chair; admin server
  access) → `ESCALATE` to human triage with: *"Based on the available IT
  knowledge base, I don't have enough information to safely resolve this
  request, so I'll route it for human review."*

Either way it never invents a policy.

### 7. How does escalation work?

Escalation happens in three situations:

- **Security** — KB-09 patterns matched in code. Always ESCALATE, HIGH, Security
  Team, with instructions to report to security@veridian-corp.example and not
  forward the message.
- **Policy conflict** — when two retrieved sources disagree and nothing says
  which wins (the 3–4 year laptop case), it escalates to the functions named in
  those policies rather than choosing.
- **No supporting policy** — routed to human triage.

An escalation produces a ticket with an "Escalated…" status, an assigned team,
and an `escalation_raised` audit event.

### 8. Why show sources?

Three reasons.

For the **employee**, it's the difference between "IT says no" and "here's the
rule, here's where it's written" — they can check it and act on it.

For **trust**, a claim with a citation is verifiable. A reviewer can open the
Knowledge Base screen and confirm the text matches.

For **debugging**, when the agent gets something wrong, the citation tells you
immediately whether retrieval failed or the decision rule was wrong. Those need
different fixes.

### 9. How is the audit trail generated?

The orchestrator owns an `_AuditRecorder`. Every stage appends a timestamped
`AuditEvent` with a stage name, a human-readable detail string, and structured
data. Timestamps increment by a millisecond so ordering is always stable.

Each interaction produces 8–11 events: request received, intent detected (and
`safety_override` if the model was overruled), retrieval with the source IDs and
scores, ticket context, policy evaluated, policy conflict if detected, decision
with priority and team, response generated, ticket created or escalation raised,
and audit record written.

They're persisted to `data/runtime/audit_log.json`, so they survive a restart,
and the UI groups them per interaction.

### 10. Why JSON / local storage instead of a database?

The supplied data pack *is* JSON, the prototype is single-user, and there are 11
policies and 25 records. A database would be setup cost and a dependency with no
demo benefit — and the brief explicitly says not to add unnecessary
infrastructure.

`DataStore` is the seam: it's the only place that reads or writes data, so
swapping in SQLite or Postgres means changing one class. There is a lock around
writes, but I wouldn't claim it's safe under real concurrent load.

### 11. How would you scale this?

In order of what breaks first:

1. **Retrieval** — BM25 over 11 documents is instant; over 10,000 it needs an
   index or embeddings. I'd swap the implementation behind the same
   `retrieve(query, topic)` interface and keep topic pinning as the safety net.
2. **Storage** — Postgres for tickets and the audit trail; the audit table is
   append-only, which fits well.
3. **The policy engine** — hand-written rules per topic don't scale past a few
   dozen policies. I'd move to a declarative rule format (policy conditions as
   data) so policy owners could edit rules without a code change.
4. **Statelessness** — the app is already stateless apart from the data store,
   so horizontal scaling is mostly a storage problem.

### 12. How would you integrate ServiceNow or Jira?

The ticket is already a structured object built in one place
(`orchestrator._build_ticket`), so I'd introduce a `TicketSink` interface with
two implementations: the current JSON writer, and a REST client that maps my
fields to theirs (`issue_summary` → summary, `assigned_team` → assignment group,
`source_policy` → a custom field or a comment).

The real work isn't the API call — it's idempotency (don't create two tickets if
a retry happens, so use a deduplication key), field mapping to their taxonomy,
and handling their API being down: queue locally and retry rather than losing
the request.

### 13. How would you implement authentication?

SSO (OIDC/SAML) at the frontend, with the backend validating the token and
taking the employee identity from it rather than a form field.

That would also improve the *agent*, not just security — knowing who the user is
means knowing their employee type, so the VPN clarifying question ("full-time or
contractor?") disappears entirely for a known user. Same for remote working days
and device age, if the directory and asset systems were connected.

Authorisation matters too: only IT staff should see other people's tickets and
the full audit trail.

### 14. How would you evaluate the agent?

A labelled evaluation set — each row is a message plus the expected decision,
expected source IDs, and expected team. Then four metrics:

- **Decision accuracy** — did it choose the right one of the five?
- **Retrieval precision** — did it cite the governing policy, and only relevant
  ones?
- **Routing accuracy** — right team?
- **Fabrication rate** — did any policy sentence appear that isn't in the
  knowledge base? This should be **zero by construction**, and I assert it.

I'd weight errors by cost: missing a security escalation is far worse than
raising an unnecessary ticket. I'd also track **over-clarification** — asking
questions that weren't needed is a real UX failure.

My 76 tests are the seed of this; a proper harness would run it in CI and fail
the build on a regression.

### 15. What happens if the LLM API fails?

It falls back to deterministic rules and keeps working — which is exactly what
happens in the demo, since I run it without a key.

Handled and tested: no API key, timeout, HTTP error (401/429/500), network
error, malformed JSON, JSON wrapped in code fences, an invented topic, invented
entity keys, an over-long summary. Each returns a readable reason instead of
raising.

The UI shows a "Demo / fallback mode" badge, the reason is in the result object
and the audit trail, and the project never describes the fallback as an LLM —
it's a keyword and regex classifier.

### 16. How did you handle the laptop policy conflict?

KB-03 says eligible after 3 years or earlier for a verified hardware failure.
ASSET-POL says a 4-year refresh cycle, with Finance sign-off in addition to IT
approval for early replacement. Nothing says which wins.

I split it into four cases rather than treating it as one:

- **≥ 4 years** — both agree. Normal ticket to IT. I don't claim a conflict
  where there isn't one.
- **3–4 years** — a genuine conflict. Retrieve both, state both positions, say
  explicitly that the supplied material doesn't say which overrides the other,
  and escalate to IT + Finance.
- **< 4 years with a reported total failure** — this is *not* a contradiction,
  it's a **combination**: KB-03 provides the early route, ASSET-POL adds the
  Finance sign-off. Escalate for verification plus both approvals.
- **< 4 years with a symptom only** — don't escalate. KB-03 needs a *verified*
  failure and a flicker isn't one, so it's a diagnostic ticket.

The second and third cases are the ones worth pointing at: recognising that two
sources can differ in one situation and stack in another. And the fourth matters
because over-escalating every laptop request would be its own failure.

One more distinction: an employee saying "it's completely dead" is a **report**,
not a **verification**. KB-03 says "verified", so the agent says verification is
still needed rather than treating the claim as confirmed.

### 17. Why shouldn't historical tickets automatically become policy?

Because a past outcome tells you what happened once, under circumstances you
can't see from the ticket — not what the rule is.

TK-1043 approved a laptop replacement at 3.2 years. If I treated that as policy,
the agent would silently resolve the exact conflict the assignment is testing,
and it would be resolving it on one data point with no visibility into whether
Finance signed off, whether there was a verified failure, or whether it was an
exception.

TK-1050 is the other side: an admin access request rejected for "no business
justification". That's useful context, and the agent shows it — but labelled
*"Closed ticket - history and precedent only, not policy"*. It can inform a
human; it can't authorise a decision.

So tickets are retrieved as **context**, displayed with that label, and the
decision rules never read them.

### 18. How do you protect sensitive information?

What's actually implemented:

- No API key is hardcoded; keys come from environment variables and `.env` is
  git-ignored.
- The agent only sends the employee's message text to the LLM, and only when a
  key is configured. No ticket history, no other employees' data.
- The knowledge base is the only business knowledge in the system — there's no
  employee directory, no credentials, no PII beyond names.
- The data pack files are read-only; generated records go to a separate
  directory so they can't be confused.

What I'd add for production, and haven't: SSO plus authorisation so employees
only see their own tickets, redaction of anything that looks like a credential
before it reaches an external API, encryption at rest, and a retention policy on
the audit log.

### 19. What would you improve with more time?

1. **Multi-turn conversations.** Today a CLARIFY is a fresh interaction — the
   employee's answer doesn't come back into the same thread. That's the biggest
   functional gap.
2. **Real integrations** — ServiceNow/Jira, the Security mailbox, SSO.
3. **The evaluation harness** from question 14, running in CI.
4. **Semantic retrieval**, keeping topic pinning as the safety net.
5. **A policy-conflict register** — once a human decides which rule wins, record
   it so the agent can apply it next time *with a citation to that decision*,
   instead of escalating the same conflict forever.

### 20. What parts of this project were generated with AI?

Most of the code was first drafted with Claude, and I've documented that fully in
[ai-tools.md](ai-tools.md) — including what I corrected.

What I decided myself: confining the LLM to understanding; the decision table
mapping topics and facts to the five decisions; the four-case treatment of the
laptop conflict; not using a vector database; and which missing facts are worth
asking about versus which questions would be noise.

What I found and fixed by testing: retrieval returning noisy citations (KB-01
showing up on a phishing report), a laptop phrasing that missed the replacement
intent, inconsistent priority on cross-function routing, and a default port that
was already occupied.

I can walk through any file in the repo and explain why it's built that way.

---

## Quick facts worth having ready

| | |
|---|---|
| Policies | 11 (KB-01…KB-10 + ASSET-POL) |
| Employee requests | 15 (REQ-01…REQ-15) |
| Tickets in the data pack | 10 — 4 active, 6 closed |
| Decisions the agent can make | 5 |
| Topics in the closed taxonomy | 12 |
| Audit events per interaction | 8–11 |
| Tests | 76, all passing |
| Backend files | 10 Python modules |
| External services required to run | none |
