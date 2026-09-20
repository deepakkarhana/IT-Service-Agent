# Assumptions

This document separates what came from the supplied assignment data pack from
what this prototype added to make a working application.

The rule applied throughout: **an implementation assumption is never presented to
the employee as company policy.**

---

## 1. Source facts — taken directly from the data pack

These are used as business knowledge and are quoted verbatim by the agent.

### Knowledge base (11 entries)

| ID | Title | The rule as supplied |
| --- | --- | --- |
| KB-01 | Password Reset | Self-service portal; lockout after 5 failed attempts needs manual IT unlock; no approval required |
| KB-02 | VPN Access | Full-time employees get access automatically; contractors need manager approval via the access request form; credentials expire every 90 days; the employee renews them |
| KB-03 | Laptop Replacement | Eligible after 3 years of service, or earlier for verified hardware failure; request at least 2 weeks ahead |
| KB-04 | Software Installation | Approved catalog software can be self-installed; non-catalog needs IT Security review taking 3–5 business days |
| KB-05 | Printer Troubleshooting | Check the queue; restart the print spooler; if it persists, log a ticket with the printer asset tag |
| KB-06 | Email Mailbox Quota | Default 25GB; archive old mail when nearing it; increase beyond 25GB needs manager approval; maximum 50GB |
| KB-07 | Guest Wi-Fi | Valid 24 hours; any employee can generate credentials at the front-desk kiosk; no IT ticket required |
| KB-08 | Expense Software | Access granted by Finance, not IT; IT assists with login/technical issues once an account exists |
| KB-09 | Security Incident Reporting | Suspected phishing, malware or unauthorized access must be reported immediately to security@veridian-corp.example; do not forward to other employees |
| KB-10 | Work-From-Home Equipment | Remote more than 3 days/week qualifies for a one-time allowance; manager sign-off; Finance processes; IT ships after approval |
| ASSET-POL | Asset Management Policy Extract | 4-year refresh cycle from date of issue; early replacement requires Finance sign-off in addition to IT approval |

### Employee requests (15)

REQ-01 … REQ-15, with employee name, request text, and the "initial action"
where the data pack supplied one (REQ-03, REQ-04, REQ-06, REQ-08, REQ-12).

### Tickets (10)

- **Active (4):** TK-1043 (laptop replacement, 3.2 years, approved – pending
  fulfilment), TK-1044 (non-catalog software, pending Security review),
  TK-1047 (home office equipment, pending Finance), TK-1048 (phishing,
  escalated to Security – under investigation).
- **Closed (6):** TK-1042 (VPN credential expired, resolved), TK-1045 (mailbox
  quota increase, approved at 35GB), TK-1046 (printer paper jam, resolved),
  TK-1049 (password reset, resolved), TK-1050 (admin access, rejected – no
  business justification), TK-1051 (guest Wi-Fi, resolved).

### The deliberate policy conflict

KB-03 (3 years) and ASSET-POL (4-year cycle + Finance sign-off for early
replacement) give different guidance. **The data pack does not say which one
takes precedence, and this prototype does not decide.** See README §14.

---

## 2. Implementation assumptions — added by this prototype

Each is listed with what was assumed and why it does not change any policy.

### 2.1 Employee email addresses — *synthetic*

The data pack supplied employee names, not contact details. Addresses were
generated as `firstname.lastname@veridian-corp.example`, using the only domain
that appears anywhere in the data pack (in KB-09's security mailbox).

*Why it is safe:* emails are display metadata only. No routing, decision or
policy depends on them, and nothing is actually sent.

### 2.2 Request dates — *synthetic*

`date_opened` values (2026-09-15 … 2026-09-19) were assigned so the queue can be
sorted and displayed. The data pack did not supply dates.

*Why it is safe:* no rule in the knowledge base depends on when a request was
opened.

### 2.3 Ticket → policy links — *derived*

`related_policy` on each supplied ticket (e.g. TK-1042 → KB-02) is a link this
prototype derived from the ticket's own issue summary. The data pack did not
supply that field.

*Why it is safe:* it is used to show related context, never to justify a
decision. The `source_policy` on a decision always comes from the policy the
agent actually retrieved.

### 2.4 `assigned_team` on supplied tickets — *only where stated*

Populated only where the supplied status names the team: TK-1044 ("Pending
Security review" → IT Security), TK-1047 ("Pending Finance" → Finance),
TK-1048 ("Escalated to Security" → Security Team), TK-1043 (IT Support, as a
laptop fulfilment). Closed tickets are left blank rather than guessed.

### 2.5 Team / routing labels — *derived from the policy text*

The agent routes to one of: `IT Support`, `IT Security`, `Security Team`,
`Finance`, `Manager approval`, `Manager approval, then Finance`,
`Finance + IT Support (joint approval)`, `No team required (self-service)`,
`IT Support (human triage)`.

Each comes from the owning function named in the policy itself — KB-04 says "IT
Security review", KB-08 says Finance grants access, KB-10 says manager sign-off
then Finance, ASSET-POL says Finance sign-off in addition to IT approval.

*What was not invented:* no org chart, no named individuals, no escalation
levels, no SLAs, no on-call rotas.

### 2.6 Prototype ticket IDs — *synthetic and clearly marked*

New tickets are numbered `NEW-1001`, `NEW-1002`, … deliberately outside the
supplied `TK-10xx` range, and are tagged **agent-created** in the UI with a
`prototype-generated` badge.

### 2.7 Ticket statuses — *descriptive, from the decision*

Statuses such as "Open – pending IT Support", "Escalated – pending IT and
Finance review", "Routed to Finance – outside IT scope" describe what the agent
decided. They are **not** claimed to be an official status taxonomy, because the
data pack does not define one. The supplied tickets keep their original status
strings unchanged.

### 2.8 Priority mapping — *the three levels the brief specifies*

`HIGH` = security incidents and privileged access; `MEDIUM` = needs human
approval or review; `LOW` = self-service or informational. No numeric scoring
system was invented. Where priority cannot be determined from what was stated,
the agent does not claim precision — it asks or escalates.

### 2.9 Issue categories — *from the knowledge base's own categories*

Account Access, Network Access, Hardware, Software, Email, Business
Applications, Security, Asset Management — all taken from the `category` field
of the supplied policies. `Unclassified` is used when nothing matches.

### 2.10 The topic taxonomy — *a closed set mapped to the policies*

Twelve topics: ten map one-to-one onto KB-01 … KB-10, plus `privileged_access`
and `unknown`, which both mean "the supplied knowledge base does not cover this".

*Why it is safe:* the set is closed, so neither the rules nor an LLM can create a
new topic — and therefore neither can create a new policy path.

### 2.11 "Reported" vs "verified" hardware failure — *a distinction, not a rule*

KB-03 says *verified* hardware failure. When an employee writes "it's completely
dead", the prototype records `reported_hardware_failure: true` and tells the
employee that verification by IT is still required.

*Why this is not an invented rule:* it is the literal reading of the word
"verified" in KB-03. The agent adds no verification procedure of its own.

### 2.12 Software catalog membership is unknown — *so it asks*

The data pack does not list what is in the approved catalog. When an employee
does not state it (REQ-14, the browser extension), the agent asks instead of
assuming. It never claims a specific product is or is not in the catalog.

### 2.13 The demo user identity

Requests submitted from the New Request screen are attributed to
`Employee (demo user)`. Requests run from the queue use the real employee name
from the data pack. There is no authentication.

### 2.14 Local JSON persistence

Generated tickets and audit events are written to `data/runtime/*.json`. The
supplied data pack files are never modified.

### 2.15 Timestamps

Audit timestamps are the real UTC time at which the prototype ran, with
millisecond increments so the stage order is stable. They are prototype
timestamps, not historical record.

---

## 3. What was explicitly **not** invented

- No company policies beyond the 11 supplied entries.
- No employee details beyond the supplied names (job titles, managers,
  departments, contract types, locations — none of these exist).
- No permissions model, approval hierarchy, escalation levels or SLAs.
- No ticket statuses claimed to be an official taxonomy.
- No resolution for the KB-03 / ASSET-POL conflict.
- No additional security procedure beyond KB-09's two instructions.
- No claim that a closed ticket sets policy — closed tickets are shown as
  precedent and labelled as such.
- No branding, company identity or product name beyond the generic
  "IT Service Agent".

## 4. What the agent says when it does not know

```
Based on the available IT knowledge base, I don't have enough information to
safely resolve this request, so I'll route it for human review.
```

This is the behaviour for any request with no matching policy — for example a
broken office chair, or the admin-access request in REQ-10.
