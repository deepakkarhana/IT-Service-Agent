# IT Service Agent

An internal service agent for IT support. An employee describes a problem in
plain English; the agent works out what the issue is, finds the policy that
governs it, and makes one explicit decision about what should happen next —
resolve it, ask a question, route it to another team, escalate it, or raise a
ticket. Every answer shows the policy it came from, and every interaction is
written to an audit trail.

---

## 1. Problem statement

An internal IT service desk receives the same kinds of requests all day: locked
accounts, expired VPN credentials, printer faults, software installs, laptop
replacements, phishing reports. Most are covered by an existing policy, but a
person still has to read the request, find the right policy, decide who owns it
and open a ticket. That is slow, and it is inconsistent — two agents can give
two different answers to the same question.

The hard part is not answering. The hard part is knowing **when not to answer**:
when the information is missing, when two policies disagree, when the request
belongs to Finance and not IT, and when something must go straight to Security.

## 2. Assignment objective

Build an internal service agent for IT support that can:

1. Understand the employee's issue
2. Find the relevant policy or resolution
3. Ask sensible follow-up questions
4. Resolve simple requests
5. Escalate risky or unclear requests
6. Create a structured ticket
7. Show the source used for its answer
8. Maintain an audit trail

## 3. Solution overview

The agent is a **pipeline of small, inspectable steps**, not one large prompt:

```
employee message
   → 1. Understand   what is the issue, what facts were stated, what is missing
   → 2. Retrieve     which policy governs this, plus related tickets
   → 3. Check policy is it resolvable / needs info / needs approval / unsupported
   → 4. Decide       RESOLVE | CLARIFY | ROUTE | ESCALATE | CREATE_TICKET
   → 5. Respond      what I understood, what the policy says, what happens next
   → 6. Ticket       a structured record, only when the decision calls for one
   → 7. Audit        every stage above, timestamped
```

The important design choice: **the language model never decides anything and
never writes policy.** It is used only to read the employee's message and return
structured facts. The decision and every policy sentence shown to the employee
come from deterministic Python that reads the knowledge base directly. Section 12
explains why.

## 4. Key agent capabilities

| Capability | How it shows up |
| --- | --- |
| Understands the issue | Extracts topic, intent, and stated facts (device age, employee type, remote days, failed attempts) without guessing the ones that were not stated |
| Finds the relevant policy | BM25 search over the knowledge base plus a topic→policy map that guarantees the governing policy is retrieved |
| Asks follow-up questions | Only when the missing fact actually changes the outcome (e.g. full-time vs contractor for VPN) |
| Resolves simple requests | Guest Wi-Fi, password reset, expired VPN credentials, mailbox archiving — no ticket raised |
| Escalates risk | Any suspected phishing/malware/unauthorised access is escalated to Security by a rule in code, not by model judgement |
| Escalates the unknown | If no policy covers the request, it says so and routes to a human instead of inventing an answer |
| Routes across departments | Expense access → Finance; home-office equipment → manager, then Finance |
| Creates structured tickets | With a synthetic `NEW-1xxx` ID so prototype tickets are never confused with the supplied queue |
| Shows its sources | Every answer lists the policy IDs it used, with the policy text |
| Maintains an audit trail | 8–11 timestamped events per interaction, persisted to disk |

## 5. Architecture

```
React + Vite frontend
        │  (HTTP, /api/*)
FastAPI backend
        │
Agent orchestrator ──────────────────────────────┐
        │                                        │
  ┌─────┴──────┬────────────┬──────────┬─────────┴────┐
  │ Understand │  Retrieve  │  Decide  │   Respond    │
  │ (rules +   │  (BM25 +   │ (policy  │ (templates + │
  │  optional  │   topic    │  engine, │  verbatim    │
  │  LLM)      │   pinning) │  pure    │  policy text)│
  └────────────┴────────────┴──────────┴──────────────┘
        │                                        │
  Ticket builder                          Audit recorder
        │                                        │
        └──────────────┬─────────────────────────┘
                       │
   data/knowledge_base.json · employee_requests.json · tickets.json
                       │
              data/runtime/  (generated tickets + audit log)
```

Full component-by-component explanation with diagrams: **[docs/architecture.md](docs/architecture.md)**.

## 6. Process flow

```
Employee → Request intake → Intent extraction → Policy retrieval
        → Ticket context retrieval → Policy / risk evaluation
        → Decision ──┬── Resolve
                     ├── Clarify
                     ├── Route
                     ├── Escalate
                     └── Create ticket
        → Response → Ticket / action record → Audit trail
```

## 7. Technology stack

| Layer | Choice | Why |
| --- | --- | --- |
| Frontend | React 18 + Vite, plain CSS | Fast to build, no CSS framework that can break mid-demo |
| Backend | Python 3 + FastAPI | Typed request/response models, automatic API docs |
| Validation | Pydantic v2 | Every stage exchanges validated objects; malformed LLM output is rejected here |
| Retrieval | BM25 implemented in ~40 lines of Python | 11 policies do not need a vector database; this has no infrastructure and is explainable |
| Storage | JSON files | The data pack is JSON; prototype records go to `data/runtime/` |
| LLM | Any OpenAI-compatible endpoint, via env vars | Optional — the app is fully functional without it |
| Tests | pytest, 76 tests | Cover all 12 required scenarios plus every LLM failure mode |

Deliberately **not** used: Kubernetes, microservices, a vector database, a real
database, authentication, message queues. This is a prototype, and each of those
would cost demo reliability without adding anything the assignment asks for.

## 8. Data sources

All business knowledge comes from three files, transcribed from the supplied
assignment data pack:

| File | Contents |
| --- | --- |
| `data/knowledge_base.json` | 10 IT policies (KB-01 … KB-10) plus the Asset Management Policy Extract (`ASSET-POL`) |
| `data/employee_requests.json` | The 15 employee requests (REQ-01 … REQ-15) |
| `data/tickets.json` | The 10 tickets (4 active, 6 closed) |

Nothing else is used as business knowledge. The Knowledge Base screen in the app
shows all 11 policies exactly as stored.

## 9. Assumptions

Full list, split into *source facts* vs *implementation assumptions*:
**[docs/assumptions.md](docs/assumptions.md)**. The short version:

- Employee email addresses and request dates are prototype metadata — the data
  pack supplied names and request text, not contact details or timestamps.
- Ticket → policy links (e.g. TK-1042 → KB-02) are derived by this prototype for
  display; the data pack did not supply that field.
- Team names come from the owning function named in the policy text itself
  (IT, IT Security, Security, Finance, manager). No org unit has been invented.
- New ticket IDs are synthetic (`NEW-1001`, `NEW-1002`, …) and labelled
  "prototype-generated" in the UI.

## 10. Agent decision flow

The agent always chooses exactly one of five decisions:

| Decision | When | Example |
| --- | --- | --- |
| `RESOLVE` | The policy fully answers it and the employee can act alone | Guest Wi-Fi (KB-07), expired VPN credentials (KB-02) |
| `CLARIFY` | One missing fact decides the outcome | "I need VPN access" — full-time or contractor? (KB-02) |
| `ROUTE_TO_OTHER_FUNCTION` | Another function owns it | Expense access → Finance (KB-08) |
| `ESCALATE` | Security risk, conflicting policy, or no policy at all | Phishing (KB-09); 3.5-year laptop (KB-03 vs ASSET-POL) |
| `CREATE_TICKET` | The policy supports it but IT must act | Account unlock after 5 failed attempts (KB-01) |

Priority is a simple three-level classification, as the brief requires — not an
invented scoring system:

- **HIGH** — security incidents and privileged-access requests
- **MEDIUM** — anything needing human approval or review
- **LOW** — self-service and informational requests

## 11. Security handling (KB-09)

Security is handled by a rule in code, not by model judgement. Fixed patterns
(phishing, malware, ransomware, unauthorised access, "asking for my password",
and others) are matched **before** anything else runs. When one matches:

- the topic is forced to `security_incident` — even if the LLM classified the
  message as something else, which is recorded in the audit trail as a
  `safety_override` event;
- the decision is always `ESCALATE`, priority `HIGH`, assigned to the Security Team;
- the employee is told to report it to `security@veridian-corp.example`
  immediately and **not to forward it to other employees**;
- if the employee says they already forwarded it, that fact is recorded in the
  escalation so Security has the full picture. No extra containment procedure is
  suggested, because the knowledge base does not define one.

`tests/test_llm_fallback.py::test_model_cannot_reclassify_a_security_incident`
proves the override holds even when the model returns `"topic": "password_reset"`.

## 12. Policy conflict handling (KB-03 vs ASSET-POL)

The data pack contains a deliberate conflict:

- **KB-03**: laptops are eligible for replacement **after 3 years**, or earlier
  for a **verified hardware failure**.
- **ASSET-POL**: all hardware follows a standard **4-year refresh cycle**, and
  early replacement requires **Finance sign-off in addition to IT approval**.

The agent does not silently pick a side. It distinguishes four situations:

| Device age | What the agent does |
| --- | --- |
| **≥ 4 years** | Both sources agree it is due. `CREATE_TICKET` to IT Support. No conflict claimed. |
| **3 – 4 years** | **Genuine conflict.** Eligible under KB-03, inside the cycle under ASSET-POL. `ESCALATE` to IT + Finance, conflict stated explicitly, and the agent says the supplied material does not say which rule overrides the other. |
| **< 4 years with a reported total failure** | Not a contradiction — the two **combine**. KB-03 gives the early-replacement route for a verified failure; ASSET-POL adds the Finance sign-off. `ESCALATE` for verification plus both approvals. |
| **< 4 years with a symptom only** | Not escalated. KB-03 requires a *verified* failure, and a flickering screen is not verified yet, so it is a `CREATE_TICKET` for a hardware check by IT. |

That last row matters: the brief warns against over-escalating every laptop
issue, and REQ-13 (2-year-old flickering screen) correctly gets a diagnostic
ticket, not an escalation.

The agent also distinguishes **reported** from **verified**. An employee saying
"it's completely dead" is a report; KB-03's earlier-replacement route needs IT to
verify it. The agent says so rather than treating the claim as confirmed.

## 13. Ticketing

A ticket is created only when the decision calls for one — `RESOLVE` and
`CLARIFY` do not create tickets, which keeps the queue clean. Each ticket holds:

`Ticket ID · Employee · Issue · Category · Priority · Decision · Next action ·
Status · Assigned team · Source policy · Created at`

New tickets use synthetic IDs starting at `NEW-1001` and are tagged
**agent-created** in the UI, so they can never be mistaken for the supplied
`TK-10xx` queue. The Tickets screen keeps **active** and **closed/history**
separate, as the data pack requires, and labels closed tickets as precedent
rather than policy.

## 14. Audit trail

Every interaction produces 8–11 timestamped events: request received, intent
detected, retrieval, ticket context, policy evaluated, policy conflict (when
detected), decision, response generated, ticket created / escalation raised, and
audit record created. Events are grouped per interaction in the UI and persisted
to `data/runtime/audit_log.json`, so the trail survives a backend restart.

## 15. LLM usage

When `LLM_API_KEY` is set, the model is asked to do exactly one job: read the
message and return JSON containing a topic (from a fixed list of 12), an intent
label, a one-line summary, and any facts the employee stated.

It does **not** decide anything, choose a team, or write policy text. Three
controls sit on top of it:

1. **Closed taxonomy** — a topic outside the 12 fails Pydantic validation and the
   result is discarded.
2. **Safety override** — security and privileged-access patterns are matched in
   code and overrule the model's classification.
3. **Regex facts win** — explicitly stated numbers and keywords ("3.5 years",
   "contractor", "not in the catalog") are extracted by regex, which is more
   precise than a model for literal detail. The model only fills the gaps.

Because the employee-facing policy text is assembled from key points copied
verbatim out of `knowledge_base.json`, a model cannot introduce a rule into the
answer even if it tries. There is a test for exactly that
(`test_policy_text_is_never_taken_from_the_model`).

## 16. Fallback / demo mode

**If no API key is set, or the LLM call fails for any reason, the application
keeps working.** The understanding step falls back to deterministic rules, and
everything downstream is unchanged.

The UI shows which mode is active in the top-right corner:

- **LLM mode** — a key is configured and the call succeeded
- **Demo / fallback mode** — no key, or the call failed (the reason is recorded
  in the result and in the audit trail)

The fallback is **not** an LLM and the project never claims it is. It is a
keyword and regex classifier. Covered failure modes, each with a test: no API
key, timeout, HTTP error, network error, malformed JSON, JSON wrapped in code
fences, an invented topic, invented entity keys, and an over-long summary.

## 17. Setup instructions

**Prerequisites:** Python 3.10+ and Node.js 18+.

### Windows (one command)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

### macOS / Linux, or manual setup

```bash
python -m venv .venv
# Windows:  .\.venv\Scripts\pip install -r backend/requirements.txt
./.venv/bin/pip install -r backend/requirements.txt

cd frontend && npm install && cd ..
cp .env.example .env        # optional - the app runs without it
```

## 18. Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `LLM_API_KEY` | *(empty)* | Enables LLM mode. Empty ⇒ demo/fallback mode. |
| `LLM_MODEL` | `gpt-4o-mini` | Model name sent to the endpoint. |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | Any OpenAI-compatible endpoint (Groq, OpenRouter, a local server). |
| `LLM_TIMEOUT_SECONDS` | `12` | After this, the agent falls back to rules. |
| `DATA_DIR` | `./data` | Where the data pack lives. |
| `VITE_API_TARGET` | `http://127.0.0.1:8020` | Backend URL the Vite dev server proxies to. |

No key is ever hardcoded. `.env` is git-ignored; `.env.example` is the template.

## 19. How to run

### Windows (one command)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
```

### macOS / Linux

```bash
bash scripts/dev.sh
```

### Two terminals (any OS)

```bash
# Terminal 1 - backend
.venv/Scripts/python -m uvicorn backend.app.main:app --port 8020 --reload

# Terminal 2 - frontend
cd frontend && npm run dev
```

Then open **http://localhost:5173**.

- Frontend: http://localhost:5173
- API: http://127.0.0.1:8020 · interactive API docs at http://127.0.0.1:8020/docs

> **Port note:** the backend defaults to **8020** rather than 8000, because 8000
> is often already taken. To change it:
> `scripts\dev.ps1 -BackendPort 8030`, or set `VITE_API_TARGET` to match.

### Tests

```bash
.venv/Scripts/python -m pytest tests/ -q          # 76 tests
.venv/Scripts/python scripts/smoke_matrix.py      # decision table for 25 requests
```

`smoke_matrix.py` prints the decision, priority, team and cited sources for a
spread of requests in one table — handy for checking nothing regressed before a
demo.

## 20. Demo scenarios

The New Request screen has one-click demo buttons for each of these.

| # | Input | Expected behaviour |
| --- | --- | --- |
| 1 | "Can I get Wi-Fi access for a guest visiting tomorrow?" | **RESOLVE**. KB-07. Front-desk kiosk, valid 24 hours, no ticket. |
| 2 | "I think I received a phishing email asking for my password." | **ESCALATE**, HIGH, Security Team. KB-09. Report to security@veridian-corp.example, do not forward. Ticket + audit entry. |
| 3 | "hey can you help, its not working" | **CLARIFY**. No sources, no guess — asks which system and what error. |
| 4 | "I need access to the expense management system." | **ROUTE** to Finance. KB-08. IT cannot grant this. |
| 5 | "My laptop is 3.5 years old and completely dead." | **ESCALATE** to IT + Finance. KB-03 **and** ASSET-POL retrieved, conflict stated, no side picked. |
| 6 | "I'm a contractor and need VPN access." | **ROUTE** for manager approval via the access request form. KB-02. No unnecessary questions — employee type was stated. |
| 7 | "I already have an expense account but I can't log in." | **CLARIFY**, stays with **IT Support** — a technical login issue, not a Finance access request. |

Two more worth showing: "My laptop screen is flickering and it is 2 years old"
(a diagnostic ticket, *not* an escalation) and "I need admin access to the
finance reporting server" (no policy exists → HIGH escalation, and TK-1050 shown
as precedent, explicitly *not* as policy).

A minute-by-minute script is in **[docs/demo-script.md](docs/demo-script.md)**.

## 21. Limitations

Honest list — these are prototype boundaries, not hidden bugs.

- **No authentication or user identity.** Everyone is "Employee (demo user)".
  A real deployment would take the identity from SSO.
- **Storage is JSON files**, not a database. Fine for one user; there is a lock
  around writes, but it is not built for concurrent load.
- **Retrieval is lexical (BM25), not semantic.** It works well on 11 policies.
  Heavy paraphrasing with no shared keywords would rely on the LLM topic
  classification instead, and on the rules if the LLM is unavailable.
- **The fallback classifier is keyword-based**, so unusual phrasing may land on
  `unknown` — which routes to a human rather than guessing, but is less fluent
  than LLM mode.
- **Nothing is actually sent anywhere.** No email is sent to Security, no ticket
  reaches ServiceNow. The agent creates records; integration is future work.
- **The agent cannot verify anything.** It cannot confirm a hardware failure, an
  employee's contract type or a manager's approval — it can only record what was
  stated and route for verification.
- **Only the 11 supplied policies are known.** Anything else is explicitly
  out of scope and escalated.

## 22. AI tools used

See **[docs/ai-tools.md](docs/ai-tools.md)** for what was AI-generated, what was
reviewed and what was tested by hand.

## 23. Future improvements

1. **Real integrations** — ServiceNow/Jira for tickets, SMTP for the Security
   mailbox, SSO for identity.
2. **Semantic retrieval** — sentence embeddings with a small local vector store,
   keeping the topic-pinning guarantee as a safety net.
3. **Multi-turn conversations** — today each `CLARIFY` is a fresh interaction;
   threading the answer back would complete the loop.
4. **An evaluation harness** — a labelled set of messages scored on decision
   accuracy, correct source, and a "never fabricates" check, run in CI.
5. **A policy-conflict register** — let IT record which policy wins once a human
   decides, so the agent can apply it next time with a cited authority.
6. **Confidence scores in the UI** — show retrieval margin so a reviewer can see
   when the agent was close to asking instead of answering.

## 24. Repository layout

```
├── backend/
│   ├── app/
│   │   ├── agent/
│   │   │   ├── understanding.py   Step 1 - deterministic classification + facts
│   │   │   ├── llm.py             Optional LLM extraction, with full fallback
│   │   │   ├── policy_engine.py   Steps 3-4 - the decision rules (pure Python)
│   │   │   ├── responder.py       Step 5 - response assembly
│   │   │   └── orchestrator.py    Pipeline order + audit trail
│   │   ├── retrieval.py           BM25 + topic pinning + ticket context
│   │   ├── data_store.py          Loads the data pack, persists runtime records
│   │   ├── models.py              Pydantic types for every stage
│   │   ├── config.py              Env-var configuration
│   │   └── main.py                FastAPI routes
│   └── requirements.txt
├── frontend/          React + Vite UI (5 screens)
├── data/              The supplied data pack + data/runtime/ for generated records
├── docs/              Architecture, assumptions, AI tools, demo script, slides, Q&A
├── scripts/           setup + dev launchers, and smoke_matrix.py
├── tests/             76 pytest tests
├── .env.example
└── README.md
```
