# Presentation — 10 slides

> **The built deck is [`IT-Service-Agent-Presentation.pptx`](IT-Service-Agent-Presentation.pptx)**
> in this folder — 10 slides, with these speaker notes already attached to each
> slide. This file is the source content behind it.

Each slide has a title, the bullets on the slide, and speaker notes. Keep the
slides light — the live demo does the work.

---

## Slide 1 — IT Service Agent

**Title:** IT Service Agent — an internal service agent for IT support

**On the slide:**
- An employee describes a problem in plain English
- The agent finds the governing policy and makes **one explicit decision**
- Resolve · Clarify · Route · Escalate · Create ticket
- Every answer shows its source. Every interaction is audited.

**Speaker notes:** The problem isn't answering questions — it's knowing when
*not* to answer. This agent is built around that.

---

## Slide 2 — The business scenario

**Title:** What an IT service desk actually deals with

**On the slide:**
- The same requests all day: locked accounts, expired VPN, printers, phishing
- Most are already covered by a written policy
- But a person still has to: read it → find the policy → work out who owns it →
  open a ticket
- Slow, and inconsistent — two agents, two answers
- **The hard cases:** missing information · two policies that disagree ·
  requests that belong to Finance · anything that must go to Security

**Speaker notes:** Mention the data pack: 11 policies, 15 employee requests,
10 tickets — and a deliberate conflict between two of the policies.

---

## Slide 3 — What the agent does

**Title:** Five things, in order

**On the slide:**

| | |
|---|---|
| **Understand** | Extracts the issue and the facts stated — without guessing the ones that weren't |
| **Retrieve** | Finds the governing policy and related tickets, and shows the source |
| **Decide** | One explicit decision, not a conversation |
| **Escalate** | Security incidents and unsupported requests always reach a human |
| **Audit** | Every stage timestamped and recorded |

**Speaker notes:** This is why it's an agent rather than a chatbot — it decides,
acts (creates the ticket, raises the escalation) and records.

---

## Slide 4 — Architecture

**Title:** How it fits together

**On the slide:**

```
React + Vite  →  FastAPI  →  Agent orchestrator
                                 │
   Understand → Retrieve → Decide → Respond → Ticket → Audit
                                 │
        knowledge_base.json · employee_requests.json · tickets.json
                                 │
                   data/runtime/  (generated tickets + audit log)
```

- LLM (optional) sits **only** on the Understand step
- Everything downstream is deterministic Python

**Speaker notes:** No vector database, no agent framework, no microservices —
11 policies don't need them, and each would add a way for the demo to fail.

---

## Slide 5 — The decision flow

**Title:** The agent makes one explicit decision

**On the slide:**

| Decision | When | Example |
|---|---|---|
| **RESOLVE** | Policy fully answers it, employee can self-serve | Guest Wi-Fi (KB-07) |
| **CLARIFY** | One missing fact decides the outcome | "I need VPN access" — full-time or contractor? |
| **ROUTE** | Another function owns it | Expense access → Finance (KB-08) |
| **ESCALATE** | Security risk, policy conflict, or no policy | Phishing (KB-09) |
| **CREATE TICKET** | Policy supports it, but IT must act | Account unlock (KB-01) |

Priority: **HIGH** security · **MEDIUM** needs approval · **LOW** self-service

**Speaker notes:** It only asks a question when the answer genuinely changes
what happens next — it doesn't ask for the sake of asking.

---

## Slide 6 — Knowledge base and retrieval

**Title:** Finding the right policy, and proving it

**On the slide:**
- 11 policies: KB-01 … KB-10 plus the Asset Management Policy Extract
- **BM25 keyword search** — ~40 lines of Python, no external service
- **Topic pinning** — guarantees the governing policy is retrieved even when the
  employee's words don't appear in it
- Every answer lists the policy IDs it used, with the policy text
- No match above threshold ⇒ **no citation is shown** — we don't imply coverage
  that doesn't exist

**Speaker notes:** Search alone isn't reliable enough to decide company policy
on; pinning alone wouldn't show retrieval is really happening. Both together
give a guaranteed-correct citation plus a visible relevance score.

---

## Slide 7 — Escalation and safety

**Title:** The parts that must never depend on a model

**On the slide:**

**Security (KB-09)** — matched by fixed patterns in code, *before* anything else
- Always ESCALATE · HIGH · Security Team
- Report to security@veridian-corp.example · do not forward
- If already forwarded, that's recorded in the escalation — no invented steps
- A model classifying it as something else is **overridden**, and the override
  is logged

**The policy conflict (KB-03 vs ASSET-POL)**
- KB-03: eligible after **3 years** · ASSET-POL: **4-year** cycle + Finance sign-off
- At 3.5 years the agent retrieves **both**, states the conflict, and **refuses
  to pick a side** — it escalates to IT + Finance
- It does **not** over-escalate: a 2-year-old flickering screen gets a diagnostic

**No policy at all** → "I don't have enough information to safely resolve this
request, so I'll route it for human review."

**Speaker notes:** This is the slide to linger on. It's the difference between a
demo and something you'd let near real employees.

---

## Slide 8 — Live demo

**Title:** Seven scenarios

**On the slide:**
1. **Guest Wi-Fi** → resolved directly, no ticket (KB-07)
2. **Phishing** → escalated to Security, HIGH (KB-09)
3. **"it's not working"** → asks what's broken, guesses nothing
4. **Expense access** → routed to Finance (KB-08)
5. **Expense login** → stays with IT — existing account, technical issue
6. **Laptop 3.5 years, dead** → conflict stated, escalated to IT + Finance
7. **Laptop 2 years, flickering** → diagnostic ticket, *not* escalated

**Speaker notes:** 4 and 5 together are the routing story. 6 and 7 together are
the judgement story.

---

## Slide 9 — Tickets and audit trail

**Title:** What gets recorded

**On the slide:**

**Structured ticket**
`ID · Employee · Issue · Category · Priority · Decision · Next action · Status ·
Assigned team · Source policy · Created at`
- Prototype tickets use synthetic `NEW-1xxx` IDs, tagged *agent-created*
- Active vs closed kept separate — closed tickets are **precedent, not policy**

**Audit trail** — 8–11 events per interaction
`request received → intent detected → KB retrieved → ticket context → policy
evaluated → conflict detected → decision → response → ticket/escalation → audit
record`
- Persisted to disk, survives a restart

**Speaker notes:** A closed ticket tells you what happened once. It doesn't make
it a rule — and the agent says so on screen.

---

## Slide 10 — Technology, limitations, next steps

**Title:** Stack, honest limits, and what's next

**On the slide:**

**Stack** — React 18 + Vite · FastAPI + Pydantic · BM25 in pure Python · JSON
storage · optional OpenAI-compatible LLM · 76 pytest tests

**Works without an LLM** — no API key ⇒ deterministic fallback mode. Timeout,
bad JSON or an invented topic all fall back cleanly. The UI shows which mode
is active.

**Limitations**
- No authentication; JSON files, not a database
- Retrieval is lexical, not semantic
- Nothing is actually sent — no real email, no ServiceNow
- The agent can't *verify* anything, only record and route

**Next steps**
1. Real ticketing + email + SSO integration
2. Semantic retrieval, keeping topic pinning as the safety net
3. Multi-turn conversations so a clarifying answer returns to the same thread
4. An evaluation harness scoring decision accuracy and "never fabricates", in CI

**Speaker notes:** Close on the design decision: the model understands, the code
decides. That's what makes it auditable.
