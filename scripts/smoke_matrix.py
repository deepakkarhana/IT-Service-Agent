"""Print the agent's decision for a spread of requests, as a single table.

Useful before a demo: one command shows every branch of the decision engine and
lets you spot a regression at a glance. Runs in deterministic mode and writes
nothing to disk.

    .venv/Scripts/python scripts/smoke_matrix.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.app.agent.orchestrator import ITServiceAgent  # noqa: E402
from backend.app.data_store import DataStore  # noqa: E402

CASES = [
    ("Demo 1  guest wifi", "Can I get Wi-Fi access for a guest visiting tomorrow?"),
    ("Demo 2  phishing", "I think I received a phishing email asking for my password."),
    ("Demo 2b phishing fwd", "I got a phishing email and already forwarded it to my teammates."),
    ("Demo 3  vague", "hey can you help, its not working"),
    ("Demo 4  expense access", "I need access to the expense management system."),
    ("Demo 5  laptop conflict", "My laptop is 3.5 years old and completely dead. Can I get a replacement?"),
    ("Demo 6  contractor vpn", "I'm a contractor and need VPN access."),
    ("Demo 7  expense login", "I already have an expense account but I can't log in. It says invalid credentials."),
    ("REQ-03  lockout", "I am locked out of my account. I tried my password 6 times."),
    ("REQ-04  non-catalog sw", "I need a data-analysis tool installed. It is not in the approved software catalog."),
    ("REQ-05  vpn expired", "My VPN stopped working. It says my credentials expired."),
    ("REQ-06  printer", "The printer on the 3rd floor keeps showing a paper jam but there is no visible jam."),
    ("REQ-07  wfh monitor", "I work from home 4 days a week. Can I get a monitor for my home desk?"),
    ("REQ-09  mailbox full", "My mailbox is full and I cannot send email any more."),
    ("REQ-10  admin access", "I need admin access to the finance reporting server."),
    ("REQ-13  flickering", "My laptop screen is flickering. The laptop is 2 years old. Repair or replacement?"),
    ("REQ-14  extension", "I would like approval to install a browser extension for productivity tracking."),
    ("Edge    vpn no type", "I need VPN access please."),
    ("Edge    laptop 5y", "My laptop is 5 years old, can I get a new one?"),
    ("Edge    laptop no age", "Can I get a laptop replacement?"),
    ("Edge    quota increase", "Can you increase my mailbox quota? I need more storage."),
    ("Edge    password simple", "I forgot my password, how do I reset it?"),
    ("Edge    printer basic", "My printer is not printing anything."),
    ("Edge    wfh no days", "Can I get a monitor for my home office?"),
    ("Edge    unsupported", "My office chair is broken and the wheel fell off."),
]


def main() -> None:
    agent = ITServiceAgent(DataStore())
    header = f"{'CASE':24s} {'DECISION':24s} {'PRI':7s} {'TEAM':38s} {'SOURCES':18s} FLAGS"
    print(header)
    print("-" * len(header))
    for name, text in CASES:
        result = agent.handle(text, employee="Smoke Test", persist=False, use_llm=False)
        sources = ",".join(s.id for s in result.sources) or "-"
        flags = []
        if result.policy_conflict and result.policy_conflict.detected:
            flags.append("CONFLICT")
        if result.ticket:
            flags.append(result.ticket.ticket_id)
        print(
            f"{name:24s} {result.decision.value:24s} {result.priority:7s} "
            f"{result.assigned_team:38s} {sources:18s} {' '.join(flags)}"
        )


if __name__ == "__main__":
    main()
