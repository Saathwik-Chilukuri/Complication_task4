"""What the app knows, and when it knows it.

Leakage rules enforced here and in pipeline.py:
  * Stages only ever see an EmailView, which has no label field.
  * A Context is a snapshot at time `now`: matters opened on or before that day, and
    filed emails with timestamp strictly before `now`.
  * Labels enter the history only after the email has been predicted (the lawyer's
    confirm/correct step), never before.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

NONE = "__none__"   # class for "belongs to no matter"


@dataclass(frozen=True)
class Person:
    name: str
    email: str

    @property
    def domain(self) -> str:
        return self.email.split("@", 1)[1].lower()


@dataclass(frozen=True)
class EmailView:
    """An email as the app sees it on arrival. There is deliberately no label here."""
    email_id: str
    thread_id: str
    in_reply_to: str | None
    references: tuple[str, ...]
    timestamp: datetime
    folder: str
    sender: Person
    to: tuple[Person, ...]
    cc: tuple[Person, ...]
    subject: str
    body: str
    attachments: tuple[str, ...]

    @classmethod
    def from_record(cls, r: dict) -> "EmailView":
        p = lambda x: Person(x["name"], x["email"].lower())
        return cls(r["email_id"], r["thread_id"], r["in_reply_to"], tuple(r["references"]),
                   datetime.fromisoformat(r["timestamp"]), r["folder"], p(r["from"]),
                   tuple(map(p, r["to"])), tuple(map(p, r["cc"])), r["subject"], r["body"],
                   tuple(r["attachments"]))

    def participants(self):
        """(role, person) for everyone on the email, deduplicated by address."""
        seen = set()
        for role, people in (("from", (self.sender,)), ("to", self.to), ("cc", self.cc)):
            for x in people:
                if x.email not in seen:
                    seen.add(x.email)
                    yield role, x


@dataclass(frozen=True)
class Matter:
    """A matter as recorded at intake."""
    matter_id: str
    matter_number: str
    name: str
    client: str
    matter_type: str
    practice_area: str
    description: str
    counterparty: str
    opposing_counsel_firm: str | None
    opened_on: date
    key_terms: tuple[str, ...]
    contacts: tuple[tuple[str, str], ...]   # (email, role) linked at intake


@dataclass(frozen=True)
class FiledEmail:
    """A past email plus the matter(s) the lawyer confirmed for it."""
    email: EmailView
    matter_ids: tuple[str, ...]             # empty = no matter


class Workspace:
    """Static facts about one app instance: the firm, the mailbox owner, matters, address book."""

    def __init__(self, inst: dict):
        self.instance_id = inst["instance_id"]
        self.firm_domain = inst["firm"]["domain"].lower()
        book = {c["contact_id"]: c for c in inst["contacts"]}
        self.owner_email = book[inst["user_contact_id"]]["email"].lower()
        self.address_book = {c["email"].lower(): c for c in inst["contacts"]}
        self.matters = [Matter(
            m["matter_id"], m["matter_number"], m["name"], m["client"], m["matter_type"],
            m["practice_area"], m["description"], m["counterparty"], m["opposing_counsel_firm"],
            date.fromisoformat(m["opened_on"]), tuple(m["key_terms"]),
            tuple((book[c["contact_id"]]["email"].lower(), c["role"]) for c in m["contacts"]),
        ) for m in inst["matters"]]

    @staticmethod
    def load(path) -> tuple["Workspace", list[dict]]:
        """Returns the workspace and the raw email records (labels included; the pipeline strips them)."""
        inst = json.loads(Path(path).read_text())
        return Workspace(inst), inst["emails"]


class Context:
    """Snapshot of what is known at time `now`. Built by the pipeline, read by stages."""

    def __init__(self, workspace: Workspace, history: list[FiledEmail], now: datetime):
        assert all(f.email.timestamp < now for f in history), "history contains future emails"
        self.workspace = workspace
        self.now = now
        self._history = history

    @property
    def open_matters(self) -> list[Matter]:
        return [m for m in self.workspace.matters if m.opened_on <= self.now.date()]

    @property
    def candidates(self) -> list[str]:
        return [m.matter_id for m in self.open_matters] + [NONE]

    @property
    def history(self) -> tuple[FiledEmail, ...]:
        return tuple(self._history)

    def thread(self, thread_id: str) -> list[FiledEmail]:
        return [f for f in self._history if f.email.thread_id == thread_id]

    def filed_under(self, matter_id: str) -> list[FiledEmail]:
        return [f for f in self._history if matter_id in f.matter_ids]
