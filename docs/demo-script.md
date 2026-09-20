# 15-minute demo script

What to say, in order, with timings. The wording is written to be spoken
naturally — don't read it word for word, but the structure and the key sentences
are worth keeping.

**Before you start:**

1. Run `powershell -ExecutionPolicy Bypass -File scripts\dev.ps1`
2. Open http://localhost:5173 and leave it on the **New Request** screen
3. Go to **Audit Trail** → **Clear prototype records**, then come back to
   New Request, so you start from a clean state
4. Have `docs/architecture.md` open in a second tab in case they ask

---

## Minute 0–2 — Problem and objective

> "This is an internal service agent for IT support.
>
> The problem it solves: an IT service desk gets the same requests all day —
> locked accounts, expired VPN credentials, printer faults, phishing reports.
> Most of them are already covered by a written policy, but a person still has
> to read the request, find the right policy, work out who owns it, and open a
> ticket. That's slow, and two agents can give two different answers to the same
> question.
>
> But the interesting part isn't answering. It's knowing **when not to answer** —
> when information is missing, when two policies disagree, when the request
> actually belongs to Finance, and when something has to go straight to Security.
>
> So what I built isn't a chatbot. It's an agent that makes one **explicit
> decision** about what should happen next: resolve it, ask a question, route it,
> escalate it, or raise a ticket. And it shows you the policy it used every time."

*(Point at the five capability cards on screen: Understand, Retrieve, Decide,
Escalate, Audit.)*

---

## Minute 2–4 — Architecture

*(Either show the diagram in `docs/architecture.md`, or just talk over the
capability cards.)*

> "The pipeline has seven steps. Understand the message. Retrieve the policy that
> governs it, plus any related tickets. Check what the policy allows. Decide.
> Respond. Create a ticket if one is needed. Write the audit trail.
>
> Here's the one design decision the whole project rests on:
> **the language model understands, but code decides.**
>
> The LLM's only job is to read the employee's message and return structured
> facts — what topic this is, and what the person actually stated. It never
> decides anything, never picks a team, and never writes policy text. The
> decision is deterministic Python, and every policy sentence on screen is copied
> **verbatim** out of the knowledge base JSON.
>
> That's deliberate. If you let a model answer policy questions, it will give you
> a confident, fluent, wrong answer — and in an internal tool that's the worst
> possible failure. This way it structurally can't invent a rule.
>
> One more thing: it's running in fallback mode right now *(point at the badge
> in the top-right)*. No API key is set, so the understanding step is running on
> deterministic rules. Everything you're about to see works with or without an
> LLM — which is also why the demo can't fail because of a network issue."

---

## Minute 4–11 — Live demo (5 scenarios)

Use the demo buttons under the text box. Click the button, click **Submit
request**, then talk through the result.

### Demo 1 — Simple resolution (~1 min)

**Click "Guest Wi-Fi" → Submit.**

> "'Can I get Wi-Fi access for a guest visiting tomorrow?'
>
> Decision: **RESOLVED**, low priority, no team required. It retrieved KB-07 —
> you can see the source card on the right with the actual policy text. It tells
> the employee to generate credentials at the front-desk kiosk, that they're
> valid 24 hours, and — importantly — **no ticket was created**, because KB-07
> explicitly says no IT ticket is required.
>
> That's the easy case. It's also the case where a lot of systems would still
> open a ticket and waste someone's time."

### Demo 2 — Security escalation (~1.5 min)

**Click "Phishing incident" → Submit.**

> "'I think I received a phishing email asking for my password, and I already
> forwarded it to my teammates to warn them.'
>
> Decision: **ESCALATED**, **HIGH** priority, Security Team. Source KB-09.
>
> It tells them to report it to security@veridian-corp.example immediately and
> not to forward it to anyone else. And because they said they'd already
> forwarded it, look at this notice — that fact is recorded in the escalation so
> Security has the full picture. It doesn't invent any extra containment steps,
> because KB-09 doesn't define any.
>
> The important bit is *how* this was classified. Security patterns are matched
> in code, **before** anything else runs. Notice the message also contains the
> word 'password' — a model could easily read this as a password reset. I have a
> test that makes a fake model return exactly that, and the code override still
> wins. Security is too important to depend on model judgement.
>
> And a ticket was created, and the whole thing is in the audit trail."

### Demo 3 — Clarifying question (~1 min)

**Click "Vague request" → Submit.**

> "'hey can you help, its not working'
>
> Decision: **CLARIFICATION REQUIRED**. And look — **no sources**, because there
> was nothing to look up, and **no ticket**.
>
> It asks: 'what isn't working? Which system, device or application, and what
> error are you seeing?'
>
> What it does *not* do is guess. It doesn't assume laptop, or VPN, or password.
> That's an easy place for an LLM-only system to hallucinate a whole support
> conversation about the wrong thing.
>
> But it only asks when the answer actually changes the outcome — I'll show you
> that in a second with the contractor VPN case."

### Demo 4 — Cross-department routing (~1.5 min)

**Click "Expense access" → Submit.**

> "'I need access to the expense management system.'
>
> Decision: **ROUTED** — to **Finance**, not IT. KB-08 says access is granted by
> Finance, and IT only helps with login problems once an account exists. So the
> agent explicitly says IT cannot grant this."

**Now click "Expense login" → Submit.** *(This is the contrast that sells it.)*

> "Now the same system, but: 'I already have an expense account but I can't log
> in — it says invalid credentials.'
>
> Different decision. This one **stays with IT Support**, because the account
> already exists, so it's a technical login issue. It doesn't dump the whole
> thing on Finance. And it asks one sensible question — for a screenshot of the
> exact error — because IT genuinely needs that to act.
>
> Same product, two requests, two correct owners. That distinction is in KB-08,
> and it's encoded in the decision rules."

### Demo 5 — Policy ambiguity (~2 min) — **the important one**

**Click "Laptop replacement" → Submit.**

> "'My laptop is 3.5 years old and completely dead. Can I get a replacement?'
>
> This is the interesting one, because the source material contains a conflict.
>
> KB-03 says laptops are eligible after **3 years**. The Asset Management Policy
> says hardware follows a **4-year refresh cycle**, and early replacement needs
> **Finance sign-off in addition to IT approval**.
>
> At 3.5 years those two give different answers. So look what it did: it
> retrieved **both** — you can see both source cards on the right — and it raised
> this red notice: *conflicting policy guidance, not resolved by the agent.* It
> states both positions and says the supplied material doesn't say which one
> overrides the other, so it won't pick.
>
> Decision: **ESCALATED**, to IT and Finance jointly, with a ticket. A human
> applies the rule and records the sign-off.
>
> It also caught something subtle: they said the laptop is dead, but KB-03 says
> earlier replacement needs a **verified** hardware failure. Reporting it isn't
> verifying it — so verification is part of the next action.
>
> And it doesn't over-escalate every laptop question."

**Click "Laptop flickering" → Submit.**

> "Same topic, 2-year-old laptop with a flickering screen. This time it's **not**
> an escalation — it's a normal diagnostic ticket to IT, low priority. Because a
> flicker isn't a verified failure yet, so the supported next step is a hardware
> check, not a replacement decision.
>
> That distinction — conflict versus combination versus 'just check it first' —
> is the part I'd most want you to look at in the code."

---

## Minute 11–13 — Tickets and audit trail

**Go to the Tickets screen.**

> "Every decision that needed one produced a structured ticket. Active tickets at
> the top — these need action — and closed tickets below, kept as history.
>
> The four TK-10xx active ones came from the data pack. These **NEW-1xxx** ones
> are the tickets the agent just created — they're tagged 'agent-created' and use
> synthetic IDs on purpose, so a prototype ticket can never be mistaken for a
> real one.
>
> Each ticket has the employee, issue, category, priority, decision, next action,
> status, assigned team, **and the source policy** — so you can always see which
> policy justified it.
>
> One thing I was careful about: the closed tickets are labelled as history and
> precedent, **not policy**. TK-1050 is an admin access request that was rejected
> for no business justification. That tells you what happened once — it doesn't
> make it a rule. The agent shows it as context and says so explicitly."

**Go to the Audit Trail screen.**

> "And here's the audit trail — every interaction, grouped, with a timestamped
> event for each stage. Request received, intent detected, KB-03 and ASSET-POL
> retrieved, ticket context, policy evaluated, **policy conflict detected**,
> decision made with the priority and team, response generated, escalation
> raised with the ticket ID, audit record written.
>
> If someone asks six months later why the agent did something, this is the
> answer. It's persisted to disk, so it survives a restart."

**Optionally, go to Request Queue.**

> "And this is all 15 requests from the data pack, triaged. You can see the
> spread — resolved, routed, escalated, clarification needed — and the policy
> conflict flagged on REQ-01. Clicking any row lets you run the full agent on it."

---

## Minute 13–15 — Technical explanation and limitations

> "Quickly on the stack: React and Vite on the front, FastAPI and Pydantic on the
> back, JSON for data. Retrieval is BM25 — I wrote it in about forty lines —
> plus a topic-to-policy map that guarantees the governing policy is always
> retrieved, even if the employee's words don't appear in it.
>
> I deliberately didn't use a vector database. There are eleven policies. An
> embedding store would add a dependency and a failure mode, and I'd *still* need
> the pinning safety net. If this grew to thousands of documents that's the first
> thing I'd swap, and the interface is already in one place.
>
> There are 76 tests covering all twelve required scenarios plus every way the
> LLM can fail — timeout, bad JSON, invented topic — and one that checks every
> policy sentence shown to the user exists **verbatim** in the knowledge base.
>
> Limitations, honestly: there's no authentication, everything is JSON files not
> a database, nothing is actually sent anywhere — no real email to Security, no
> ServiceNow. Retrieval is lexical, not semantic. And the agent can't *verify*
> anything — it can't confirm a hardware failure or a manager's approval, it can
> only record what was stated and route it for verification.
>
> With more time, the next things I'd build are real ticketing and email
> integration, multi-turn conversations so a clarifying answer comes back into
> the same thread, and an evaluation harness that scores decision accuracy and
> 'never fabricates' on a labelled set, running in CI."

---

## If you have spare time

- **Knowledge Base screen** — "these eleven entries are the agent's only source
  of business knowledge. Nothing outside this list is used."
- **Admin access demo** — "no policy covers privileged access, so it escalates
  and says so rather than inventing an approval process."
- **Show the code** — `backend/app/agent/policy_engine.py`, the
  `_laptop` function, is the best thing to show.

## Questions you should expect

Full answers in [interview-questions.md](interview-questions.md). The three most
likely:

- *"Why is this an agent and not a chatbot?"* → It doesn't just reply; it makes
  an explicit decision, takes an action (creates a ticket, escalates), and
  records it.
- *"How do you stop it hallucinating policy?"* → The model can't write policy
  text. Answers are assembled from key points copied verbatim from the JSON, and
  a test proves it.
- *"What if the LLM API fails?"* → It already does, in the demo you just watched.
  It falls back to deterministic rules and the UI tells you which mode it's in.
