# AI tools used

An honest account of which AI tools were used to build this project, what they
produced, and what was reviewed and tested by hand.

---

## 1. Tools used during development

### Claude (Anthropic) — via Claude Code

**Used for:** architecture design, code generation, debugging, and drafting
documentation.

Specifically:

- Designing the seven-step pipeline and the split between LLM understanding and
  deterministic decision-making.
- Generating the first version of most source files: the FastAPI backend, the
  BM25 retriever, the policy engine, the React components and the CSS.
- Transcribing the supplied data pack into the three structured JSON files.
- Writing the pytest suite.
- Drafting this documentation set.

### VS Code

Editor used throughout, including the integrated terminal for running the
backend, the frontend dev server and the tests.

### Git / GitHub

Version control and submission.

### An LLM API at runtime (optional)

The application can call any OpenAI-compatible chat completions endpoint for the
understanding step. **It is optional** — the project ships with no key and runs
in deterministic fallback mode by default. No provider is required to run or
demo the project.

---

## 2. What was AI-generated

Essentially all of the source code was first drafted with AI assistance:

| Area | AI-generated | Notes |
| --- | --- | --- |
| Backend structure (FastAPI, Pydantic models, routes) | Yes | Layout and naming refined during review |
| BM25 retriever | Yes | Scoring thresholds tuned by hand after inspecting real scores (see §3) |
| Policy engine decision rules | Yes, from a hand-specified decision table | The rules themselves were decided against the data pack first, then written |
| React components and CSS | Yes | Layout adjusted after looking at rendered screenshots |
| JSON data files | Transcribed from the supplied data pack | Checked line by line against the source material |
| pytest suite | Yes | Assertions were written to match expected behaviour derived from the policies, not from the implementation's output |
| README and docs | Yes, drafted | Reviewed for accuracy against the actual code |

---

## 3. What was reviewed, corrected and tested by hand

AI drafts were not accepted as-is. The following were found and fixed during
review and testing:

1. **Retrieval was returning noisy citations.** The first version showed KB-01
   (Password Reset) as a supporting source for a phishing report, and KB-06
   (Mailbox Quota) for a laptop question, because words like "password" and
   "old" appear in several policies. Actual BM25 scores were printed and
   inspected, and a two-part gate was added: an absolute floor plus 70% of the
   best score for that query. Citations are now clean.

2. **A laptop phrasing was misrouted.** "My laptop is 5 years old, can I get a
   new one?" did not match the replacement-intent pattern and fell through to
   the diagnostic branch. The pattern was widened to cover "a new
   laptop/machine/device/computer/one".

3. **Routing priority was inconsistent.** An expense access request routed to
   Finance was classified LOW while other cross-function routings were MEDIUM.
   It was made MEDIUM for consistency: anything requiring another function to
   act is a human-approval path.

4. **Port 8000 was occupied** on the development machine, so the default backend
   port was moved to 8020 and made configurable, rather than shipping a default
   that fails on first run.

5. **A corrupted CSS value** (`--muted: #667competition;`) slipped into the
   first stylesheet draft and was removed.

6. **A missing favicon** was producing a console 404; an inline SVG icon was
   added.

Testing that was actually performed:

- All **76 pytest tests** run and pass.
- Every one of the **26 scenarios** in the smoke matrix was run and the decision,
  priority, team and cited sources were checked by hand against the policy text.
- The UI was **rendered and inspected in a real browser** (screenshots of all
  five screens) to confirm the layout, the conflict notice, the audit timeline
  and the ticket panel display correctly, and that the console is clean.
- The **LLM failure paths were simulated** — timeout, HTTP error, network error,
  malformed JSON, invented topic, invented entity keys — and each one confirmed
  to fall back cleanly rather than break the app.
- The **safety override was tested adversarially** by making a stub model return
  `"topic": "password_reset"` for a phishing message, confirming the code
  override wins.

---

## 4. What was decided by a human, not by AI

- That the LLM would be confined to understanding, and never allowed to decide
  or to write policy text.
- The decision table: which of the five decisions each topic and fact
  combination produces.
- The treatment of the KB-03 / ASSET-POL conflict — in particular the choice to
  distinguish the *conflict* zone (3–4 years) from the *combination* case
  (under 4 years with a verified failure), rather than escalating every laptop
  request.
- The choice not to use a vector database.
- Which facts count as "missing information" worth asking about, and which
  questions would be unnecessary.

---

## 5. Honesty note

No tool is claimed here that was not used. In particular:

- No vector database, embedding model or agent framework (LangChain, LlamaIndex,
  CrewAI, AutoGen) is used anywhere in this project.
- The deterministic fallback mode is **not** an LLM and is never described as
  one, in the code, the UI or the documentation.
- The runtime LLM integration is real and works, but the project is demonstrated
  in fallback mode by default so the demo does not depend on an external API.
