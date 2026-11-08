"""Synthetic data generator for email -> matter classification.

One *instance* = one law-firm workspace in the app: a lawyer (the mailbox owner),
their firm, a set of open matters, the contacts involved, and the emails in the
lawyer's mailbox. Every email carries a ground-truth label plus diagnostics that
explain *why* it is easy or hard. See SCHEMA.md.

Usage:
    python generate_data.py                  # 50 instances + small example, seed 7
    python generate_data.py --instances 200 --seed 1 --out data
"""

import argparse
import json
import random
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import templates as T

START = datetime(2026, 6, 1, 9, 0)

DEFAULT_CFG = dict(
    matters=(3, 6),            # matters per instance
    threads=(3, 5),            # threads per matter
    msg_weights=[0.35, 0.30, 0.20, 0.15],  # P(thread has 1, 2, 3, 4 messages)
    generic=(1, 3),            # content-free emails tied to a matter
    new_sender=(1, 2),         # emails from people not yet in the matter's contacts
    no_matter=(2, 4),          # emails that belong to no matter
    p_shared_client=0.6,       # one client has 2+ matters
    p_shared_opposing=0.4,     # two matters share opposing counsel
    p_dup_type=0.2,            # two matters of the same practice type
    p_drift=0.7,               # per shared client: a thread that changes topic to another matter
    status_report=True,        # associate's weekly status email covering several matters
    p_prebill=0.4,             # per client: billing email listing their matter numbers
    quote_prob=0.75,           # replies quote the previous message
)

# ~10-email example in the spirit of the assignment: 3 matters, one shared client.
SMALL_CFG = dict(DEFAULT_CFG, matters=(3, 3), threads=(1, 2), msg_weights=[0.6, 0.4, 0, 0],
                 generic=(1, 1), new_sender=(1, 1), no_matter=(1, 1), p_shared_client=1.0,
                 p_shared_opposing=0.0, p_dup_type=0.0, p_drift=0.0, status_report=False,
                 p_prebill=0.0)


def fmt_date(d):
    return f"{d:%B} {d.day}"


class Instance:
    def __init__(self, rng, iid, cfg):
        self.rng, self.iid, self.cfg = rng, iid, cfg
        self.contacts, self.matters, self.emails = {}, [], []
        self.used_names, self.used_prefixes, self.used_agencies = set(), set(), set()
        self.reserved_last = set()   # plaintiff surnames; never reused so they stay identifying
        self.n_threads = 0

    # ------------------------------------------------------------------ names / orgs
    def _last(self):
        return self.rng.choice([l for l in T.LAST_NAMES if l not in self.reserved_last])

    def person_name(self):
        while True:
            f, l = self.rng.choice(T.FIRST_NAMES), self._last()
            if (f, l) not in self.used_names:
                self.used_names.add((f, l))
                return f, l

    def _prefix(self):
        p = self.rng.choice([p for p in T.CO_PREFIX if p not in self.used_prefixes])
        self.used_prefixes.add(p)
        return p

    def make_org(self, kind):
        if kind == "law_firm":
            l1, l2 = self.rng.sample([l for l in T.LAST_NAMES if l not in self.reserved_last], 2)
            return dict(name=f"{l1} & {l2} LLP", short=l1, domain=f"{l1}{l2}.com".lower(), kind=kind)
        if kind == "agency":
            name, short, domain = self.rng.choice([a for a in T.AGENCIES if a[0] not in self.used_agencies])
            self.used_agencies.add(name)
            return dict(name=name, short=short, domain=domain, kind=kind)
        p = self._prefix()
        tmpl, dom = T.ORG_KINDS[kind]
        if kind == "company":
            s = self.rng.choice(T.CO_SUFFIX)
            return dict(name=f"{p} {s}", short=p, domain=f"{p}{s[:4]}.com".lower(), kind=kind)
        return dict(name=tmpl.format(p=p), short=p, domain=f"{p.lower()}{dom}", kind=kind)

    def add_contact(self, org, title, internal=False):
        f, l = self.person_name()
        cid = f"{self.iid}-c{len(self.contacts):03d}"
        local = self.rng.choice([f"{f}.{l}", f"{f[0]}{l}", f"{f}{l[0]}"]).lower()
        sig = f"\n{title}\n{org['name']}" if self.rng.random() < 0.7 else ""
        if internal and self.rng.random() < 0.6:
            sig += ("\n\nCONFIDENTIALITY NOTICE: This message may contain attorney-client privileged "
                    "or confidential information. If you received it in error, please delete it.")
        self.contacts[cid] = dict(contact_id=cid, name=f"{f} {l}", first=f, email=f"{local}@{org['domain']}",
                                  organization=org["name"], org_type=org["kind"], title=title,
                                  is_internal=internal, _sig=sig)
        return cid

    # ------------------------------------------------------------------ setup
    def build(self):
        rng, cfg = self.rng, self.cfg
        self.firm = self.make_org("law_firm")
        self.firm["kind"] = "own_firm"
        self.user = self.add_contact(self.firm, "Partner", internal=True)
        self.assocs = [self.add_contact(self.firm, rng.choice(["Associate", "Senior Associate"]), internal=True)
                       for _ in range(rng.randint(2, 3))]
        self.billing = self.add_contact(self.firm, "Billing Coordinator", internal=True)

        n = rng.randint(*cfg["matters"])
        types = rng.sample(list(T.MATTER_TYPES), n)
        if n > 1 and rng.random() < cfg["p_dup_type"]:
            types[-1] = types[0]

        # client assignment: clients[i] is the client index for matter i
        clients = list(range(n))
        if n > 1 and rng.random() < cfg["p_shared_client"]:
            a, b = rng.sample(range(n), 2)
            if types[a] != types[b]:
                clients[b] = clients[a]
        self.clients = {}
        for ci in sorted(set(clients)):
            org = self.make_org("company")
            self.clients[ci] = dict(org=org, client_no=rng.randint(10000, 99999), n_matters=0,
                                    gc=self.add_contact(org, "General Counsel"), matter_ids=[])

        # opposing-counsel sharing plan
        firm_sides = [i for i, t in enumerate(types)
                      if T.MATTER_TYPES[t]["opposing"] and T.MATTER_TYPES[t]["opposing"][0] == "law_firm"]
        share_opp = {}
        if len(firm_sides) >= 2 and rng.random() < cfg["p_shared_opposing"]:
            a, b = rng.sample(firm_sides, 2)
            share_opp[max(a, b)] = min(a, b)

        for i, t in enumerate(types):
            self.make_matter(t, self.clients[clients[i]], share_opp.get(i))

    def make_matter(self, mtype, client, share_from):
        rng, spec = self.rng, T.MATTER_TYPES[mtype]
        mid = f"{self.iid}-m{len(self.matters):02d}"
        client["n_matters"] += 1
        client["matter_ids"].append(mid)
        corg = client["org"]
        opened = START + timedelta(days=rng.randint(0, 60))

        s = dict(client=corg["name"], client_short=corg["short"],
                 mnum=f"{client['client_no']}-{client['n_matters']:03d}",
                 code=rng.choice(T.CODENAMES),
                 amount=f"${rng.choice([85, 120, 240, 410, 650])} million" if mtype == "acquisition"
                 else f"${rng.choice([18, 25, 40, 60])} million",
                 amount_small=f"${rng.choice(['450,000', '780,000', '1.2 million', '2.5 million'])}",
                 valuation=f"${rng.choice([90, 140, 220, 310])} million",
                 round=rng.choice(["Series A", "Series B", "Series C"]),
                 case_no=f"{rng.randint(3, 5)}:26-cv-{rng.randint(1000, 9999):05d}",
                 address=f"{rng.randint(100, 2999)} {rng.choice(T.STREETS)}",
                 cid=f"{rng.randint(2025, 2026)}-{rng.randint(100, 999)}")
        pnum = rng.randint(100, 999)
        s.update(patent=f"10,{pnum},{rng.randint(100, 999)}", patent_short=str(pnum))

        if spec["cp_kind"] == "person":
            f, l = self.person_name()
            while l in self.reserved_last or any(c["name"].endswith(" " + l) for c in self.contacts.values()):
                f, l = self.person_name()
            self.reserved_last.add(l)
            s.update(plaintiff=f"{f} {l}", plaintiff_last=l, cp=f"{f} {l}", cp_short=l)
            cp_org = None
        else:
            cp_org = self.make_org(spec["cp_kind"])
            s.update(cp=cp_org["name"], cp_short=cp_org["short"], plaintiff="", plaintiff_last="")
        self.used_codes = getattr(self, "used_codes", set())
        while s["code"] in self.used_codes:
            s["code"] = rng.choice(T.CODENAMES)
        self.used_codes.add(s["code"])

        roles = dict(user=[self.user], gc=[client["gc"]],
                     assoc=rng.sample(self.assocs, rng.choice([1, 1, 2])),
                     client=[self.add_contact(corg, spec["client_title"])])
        opp_org = None
        if spec["opposing"]:
            kind, title = spec["opposing"]
            if kind == "agency":
                opp_org = cp_org
                roles["opposing"] = [self.add_contact(opp_org, title)]
            elif share_from is not None:
                src = self.matters[share_from]
                opp_org = src["_opp_org"]
                if rng.random() < 0.5:
                    roles["opposing"] = list(src["_roles"]["opposing"])
                else:
                    roles["opposing"] = [self.add_contact(opp_org, title)]
            else:
                opp_org = self.make_org(kind)
                roles["opposing"] = [self.add_contact(opp_org, title)]
        if spec["cp_contact"]:
            roles["cp"] = [self.add_contact(cp_org, spec["cp_contact"])]
        trole, tkind, ttitle = spec["third"]
        roles["third"] = [self.add_contact(self.make_org(tkind), ttitle)]

        role_names = dict(gc="client_general_counsel", client="client_contact", assoc="internal_team",
                          opposing="opposing_counsel", cp="counterparty", third=trole)
        key_terms = list(dict.fromkeys(k.format(**s) for k in spec["key_terms"] if k.format(**s)))
        self.matters.append(dict(
            matter_id=mid, matter_number=s["mnum"], name=spec["name"].format(**s),
            client=corg["name"], matter_type=mtype, practice_area=spec["practice_area"],
            description=spec["description"].format(**s), counterparty=s["cp"],
            opposing_counsel_firm=opp_org["name"] if opp_org else None,
            status="open", opened_on=opened.date().isoformat(), key_terms=key_terms,
            contacts=[dict(contact_id=c, role=role_names[r]) for r, cs in roles.items() if r != "user" for c in cs],
            _spec=spec, _slots=s, _roles=roles, _opened=opened, _opp_org=opp_org, _client=client))

    # ------------------------------------------------------------------ email helpers
    def biz(self, ts):
        if ts.hour >= 21:
            ts = (ts + timedelta(days=1)).replace(hour=self.rng.randint(7, 9))
        elif ts.hour < 7:
            ts = ts.replace(hour=self.rng.randint(7, 9))
        while ts.weekday() >= 5:
            ts = (ts + timedelta(days=1)).replace(hour=self.rng.randint(8, 10))
        return ts

    def slots(self, matter, ts, to_ids):
        rng = self.rng
        d1 = ts + timedelta(days=rng.randint(7, 25))
        s = dict(matter["_slots"]) if matter else {}
        s.update(to_first=self.contacts[to_ids[0]]["first"] if to_ids else "",
                 assoc_first=self.contacts[rng.choice(matter["_roles"]["assoc"] if matter else self.assocs)]["first"],
                 day=rng.choice(T.WEEKDAYS), time=rng.choice(T.TIMES),
                 date=fmt_date(d1), date2=fmt_date(d1 + timedelta(days=rng.randint(3, 10))))
        return s

    def greeting(self, sender, to):
        rng, c = self.rng, self.contacts
        if len(to) > 1 and rng.random() < 0.5:
            return rng.choice(["All,", "Hi all,", "Hi everyone,"])
        s, r = c[sender], c[to[0]]
        if s["org_type"] in ("law_firm", "agency", "own_firm") and r["org_type"] in ("law_firm", "agency", "own_firm") \
                and s["organization"] != r["organization"] and rng.random() < 0.5:
            return "Counsel,"
        return rng.choice(["Hi {f},", "{f},", "Hello {f},", "Dear {f},"]).format(f=r["first"])

    def emit(self, ts, sender, to, cc, subject, text, thread_id, label, parent=None, attach=()):
        to = [x for x in dict.fromkeys(to) if x != sender]
        cc = [x for x in dict.fromkeys(cc) if x != sender and x not in to]
        assert self.user in [sender] + to + cc, "mailbox owner must be on every email"
        c = self.contacts
        head = f"{self.greeting(sender, to)}\n\n{text}"
        body = f"{head}\n\n{self.rng.choice(['Best,', 'Thanks,', 'Regards,', 'Best regards,'])}\n" \
               f"{c[sender]['name'] if self.rng.random() < 0.6 else c[sender]['first']}{c[sender]['_sig']}"
        if parent and self.rng.random() < self.cfg["quote_prob"]:
            p = c[parent["_sender"]]
            quoted = "\n".join(("> " + ln) if ln else ">" for ln in parent["_head"].split("\n"))
            body += f"\n\nOn {parent['_ts']:%a, %b %d, %Y at %I:%M %p}, {p['name']} <{p['email']}> wrote:\n{quoted}"
        person = lambda x: dict(name=c[x]["name"], email=c[x]["email"])
        e = dict(email_id=None, thread_id=thread_id,
                 in_reply_to=parent["_key"] if parent else None,
                 references=(parent["references"] + [parent["_key"]]) if parent else [],
                 timestamp=None, folder="sent" if sender == self.user else "inbox",
                 **{"from": person(sender)}, to=[person(x) for x in to], cc=[person(x) for x in cc],
                 subject=subject, body=body, attachments=list(attach), label=label,
                 _key=len(self.emails), _ts=ts, _sender=sender, _head=head, _to=to, _cc=cc)
        self.emails.append(e)
        return e

    def new_thread(self):
        self.n_threads += 1
        return self.n_threads

    def reply_chain(self, first, n_more, label_fn):
        """Append n_more reply-all messages to the thread started by `first`."""
        rng, prev = self.rng, first
        participants = [first["_sender"]] + first["_to"] + first["_cc"]
        for _ in range(n_more):
            last = prev["_sender"]
            if last != self.user:
                responder = self.user
            else:
                responder = rng.choice(prev["_to"] or [p for p in participants if p != self.user])
            ts = self.biz(prev["_ts"] + timedelta(hours=rng.uniform(0.5, 50)))
            to = [last]
            cc = [p for p in participants if p not in (responder, last)]
            subj = first["subject"] if first["subject"].startswith("Re: ") else "Re: " + first["subject"]
            text = rng.choice(T.REPLIES).format(**self.slots(self.matter_of(first), ts, to))
            prev = self.emit(ts, responder, to, cc, subj, text, first["thread_id"], label_fn(), parent=prev)
        return prev

    def matter_of(self, email):
        pid = email["label"]["primary_matter_id"]
        return next((m for m in self.matters if m["matter_id"] == pid), None)

    def pick(self, matter, role):
        return self.rng.choice(matter["_roles"][role])

    def thread_start(self, matter):
        return self.biz(matter["_opened"] + timedelta(days=self.rng.uniform(0, 80), hours=self.rng.uniform(0, 9)))

    @staticmethod
    def label(matters, scenario, primary=None):
        ids = [m["matter_id"] for m in matters]
        return dict(primary_matter_id=primary or (ids[0] if ids else None), matter_ids=ids, scenario=scenario)

    # ------------------------------------------------------------------ email scenarios
    def matter_threads(self):
        rng, cfg = self.rng, self.cfg
        for m in self.matters:
            spec = m["_spec"]
            openers = rng.sample(spec["openers"], min(rng.randint(*cfg["threads"]), len(spec["openers"])))
            for op in openers:
                ts = self.thread_start(m)
                sender = self.pick(m, op["frm"])
                to = [self.pick(m, r) for r in op["to"]]
                cc = [self.pick(m, r) for r in op["cc"] if r in m["_roles"]]
                s = self.slots(m, ts, to)
                first = self.emit(ts, sender, to, cc, op["subject"].format(**s), op["body"].format(**s),
                                  self.new_thread(), self.label([m], "matter_thread"),
                                  attach=[a.format(**s) for a in op.get("attach", [])])
                n = rng.choices([1, 2, 3, 4], weights=cfg["msg_weights"])[0]
                self.reply_chain(first, n - 1, lambda: self.label([m], "thread_reply"))

    def generic_emails(self):
        rng = self.rng
        for _ in range(rng.randint(*self.cfg["generic"])):
            m = rng.choice(self.matters)
            tmpl = rng.choice([g for g in T.GENERIC if g["frm"] in m["_roles"]])
            ts = self.thread_start(m)
            sender = self.pick(m, tmpl["frm"])
            s = self.slots(m, ts, [self.user])
            self.emit(ts, sender, [self.user], [], tmpl["subject"], tmpl["body"].format(**s),
                      self.new_thread(), self.label([m], "generic_content"))

    def cross_matter_emails(self):
        rng, cfg = self.rng, self.cfg
        for client in self.clients.values():
            ms = [m for m in self.matters if m["_client"] is client]
            if len(ms) >= 2:
                a, b = rng.sample(ms, 2)
                ts = self.biz(max(a["_opened"], b["_opened"]) + timedelta(days=rng.uniform(5, 70)))
                lines = [x["_spec"]["drift"].format(**self.slots(x, ts, [self.user])) for x in (a, b)]
                text = "Two quick things.\n\n" + "\n".join(f"{i + 1}. {ln[0].upper() + ln[1:]}" for i, ln in enumerate(lines))
                self.emit(ts, client["gc"], [self.user], [], "A couple of things", text,
                          self.new_thread(), self.label([a, b], "multi_matter"))

                # topic drift: GC thread about A turns to B
                if rng.random() < cfg["p_drift"]:
                    op = next(o for o in a["_spec"]["openers"] if o["frm"] == "gc")
                    ts = self.thread_start(a)
                    s = self.slots(a, ts, [self.user])
                    first = self.emit(ts, client["gc"], [self.user], [], op["subject"].format(**s),
                                      op["body"].format(**s), self.new_thread(), self.label([a], "matter_thread"))
                    mid = self.reply_chain(first, 1, lambda: self.label([a], "thread_reply"))
                    ts = self.biz(mid["_ts"] + timedelta(hours=rng.uniform(1, 30)))
                    text = T.DRIFT_LEAD.format(drift=b["_spec"]["drift"].format(**self.slots(b, ts, [self.user])))
                    self.emit(ts, client["gc"], [self.user], [], "Re: " + first["subject"], text, first["thread_id"],
                              self.label([b, a], "topic_drift"), parent=mid)

            if rng.random() < cfg["p_prebill"]:
                ts = self.biz(START + timedelta(days=rng.choice([60, 91, 121]), hours=rng.uniform(0, 8)))
                lines = "\n".join(f"- {m['matter_number']}  {m['name']}" for m in ms)
                text = (f"Pre-bills for {client['org']['name']} are ready for your review:\n\n{lines}\n\n"
                        f"Please mark up and return by {fmt_date(ts + timedelta(days=4))}.")
                self.emit(ts, self.billing, [self.user], [], f"Pre-bills for review - {client['org']['short']}",
                          text, self.new_thread(), self.label(ms, "billing_multi" if len(ms) > 1 else "billing"))

        if cfg["status_report"]:
            busy = [a for a in self.assocs if sum(a in m["_roles"]["assoc"] for m in self.matters) >= 2]
            if busy:
                a = rng.choice(busy)
                ms = [m for m in self.matters if a in m["_roles"]["assoc"]]
                ts = self.biz(START + timedelta(days=rng.uniform(70, 140)))
                lines = "\n".join("- " + m["_spec"]["status"].format(**self.slots(m, ts, [self.user])) for m in ms)
                self.emit(ts, a, [self.user], [], "Weekly matter status", f"Status on my matters this week:\n\n{lines}",
                          self.new_thread(), self.label(ms, "multi_matter_status"))

    def new_sender_emails(self):
        rng = self.rng
        for _ in range(rng.randint(*self.cfg["new_sender"])):
            m = rng.choice(self.matters)
            ns = m["_spec"]["new_sender"]
            org = m["_opp_org"] if ns["org"] == "opposing" else self.make_org(ns["org"].split(":")[1])
            sender = self.add_contact(org, ns["title"])   # deliberately NOT added to the matter's contacts
            ts = self.thread_start(m)
            s = self.slots(m, ts, [self.user])
            cc = [self.pick(m, "assoc")] if rng.random() < 0.4 else []
            self.emit(ts, sender, [self.user], cc, ns["subject"].format(**s), ns["body"].format(**s),
                      self.new_thread(), self.label([m], "new_sender"))

    def no_matter_emails(self):
        rng = self.rng
        for nm in rng.sample(T.NO_MATTER, rng.randint(*self.cfg["no_matter"])):
            org = self.firm if nm["org"] == "internal" else self.make_org(nm["org"].split(":")[1])
            sender = self.add_contact(org, nm["title"], internal=nm["org"] == "internal")
            ts = self.biz(START + timedelta(days=rng.uniform(0, 140), hours=rng.uniform(0, 9)))
            scen = "no_matter_keyword_trap" if nm.get("trap") else "no_matter"
            self.emit(ts, sender, [self.user], [], nm["subject"], nm["body"], self.new_thread(), self.label([], scen))

    # ------------------------------------------------------------------ finalize
    def diagnose(self):
        """Compute what metadata vs. text alone say about each email, and a difficulty grade."""
        c = self.contacts
        by_email = {x["email"]: x for x in c.values()}
        contact_m, domain_m = {}, {}
        for m in self.matters:
            for mc in m["contacts"]:
                em = c[mc["contact_id"]]["email"]
                contact_m.setdefault(em, set()).add(m["matter_id"])
                if not c[mc["contact_id"]]["is_internal"]:
                    domain_m.setdefault(em.split("@")[1], set()).add(m["matter_id"])
        by_key = {e["_key"]: e for e in self.emails}
        user_email = c[self.user]["email"]

        for e in self.emails:
            truth = set(e["label"]["matter_ids"])
            people = [e["from"]] + e["to"] + e["cc"]
            score = Counter()
            for p in people:
                if p["email"] == user_email:
                    continue
                ms = contact_m.get(p["email"]) or domain_m.get(p["email"].split("@")[1], set())
                score.update(ms)
            top = max(score.values(), default=0)
            part = {k for k, v in score.items() if v == top} if top else set()
            parent = by_key.get(e["in_reply_to"]) if e["in_reply_to"] is not None else None
            thread = set(parent["label"]["matter_ids"]) if parent else None
            meta = thread if parent else part

            text = e["subject"] + "\n" + e["body"]
            ids = {m["matter_id"] for m in self.matters
                   if any(re.search(r"(?<!\w)" + re.escape(t) + r"(?!\w)", text) for t in m["key_terms"])}
            low = text.lower()
            kws = {m["matter_id"] for m in self.matters
                   if sum(bool(re.search(r"(?<!\w)" + re.escape(k) + r"(?!\w)", low)) for k in m["_spec"]["keywords"]) >= 2}
            content = ids or kws

            meta_ok, content_ok = meta == truth, content == truth
            diff = {2: "obvious", 1: "moderate", 0: "ambiguous"}[meta_ok + content_ok]
            reasons = []
            if not parent and not part:
                reasons.append("unknown_participants")
            if len(part) > 1:
                reasons.append("participants_span_multiple_matters")
            if parent and thread != truth:
                reasons.append("thread_topic_changed")
            if not ids and not kws:
                reasons.append("no_matter_specific_text")
            if ids - truth:
                reasons.append("identifiers_point_elsewhere")
            if not ids and kws - truth:
                reasons.append("keywords_match_other_matter")
            if len(truth) > 1:
                reasons.append("spans_multiple_matters")
                diff = "ambiguous"
            sender = by_email.get(e["from"]["email"])
            if sender and sender["is_internal"] and sender["contact_id"] != self.user:
                reasons.append("internal_sender")

            e["label"].update(difficulty=diff, ambiguity_reasons=reasons, signals=dict(
                participant_candidates=sorted(part), thread_candidates=sorted(thread) if parent else None,
                identifier_candidates=sorted(ids), keyword_candidates=sorted(kws),
                metadata_points_to_truth=meta_ok, text_points_to_truth=content_ok))

    def finalize(self):
        self.emails.sort(key=lambda e: e["_ts"])
        new_id = {e["_key"]: f"{self.iid}-e{i:03d}" for i, e in enumerate(self.emails)}
        thread_ids = {}
        for e in self.emails:
            thread_ids.setdefault(e["thread_id"], f"{self.iid}-t{len(thread_ids):03d}")
        self.diagnose()
        cut = int(len(self.emails) * 0.6)
        for i, e in enumerate(self.emails):
            e["email_id"] = new_id[e["_key"]]
            e["thread_id"] = thread_ids[e["thread_id"]]
            e["in_reply_to"] = new_id[e["in_reply_to"]] if e["in_reply_to"] is not None else None
            e["references"] = [new_id[k] for k in e["references"]]
            e["timestamp"] = e["_ts"].isoformat()
            e["split"] = "history" if i < cut else "incoming"
        strip = lambda d: {k: v for k, v in d.items() if not k.startswith("_")}
        return dict(
            instance_id=self.iid,
            firm=dict(name=self.firm["name"], domain=self.firm["domain"]),
            user_contact_id=self.user,
            matters=[strip(m) for m in self.matters],
            contacts=[strip(x) for x in self.contacts.values()],
            emails=[strip(e) for e in self.emails],
        )


def make_instance(seed, iid, cfg=DEFAULT_CFG):
    inst = Instance(random.Random(seed), iid, cfg)
    inst.build()
    inst.matter_threads()
    inst.generic_emails()
    inst.cross_matter_emails()
    inst.new_sender_emails()
    inst.no_matter_emails()
    out = inst.finalize()
    out["seed"] = seed
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instances", type=int, default=50)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="data")
    args = ap.parse_args()

    out = Path(args.out)
    (out / "instances").mkdir(parents=True, exist_ok=True)
    flat, diff, scen = [], Counter(), Counter()
    for i in range(args.instances):
        inst = make_instance(args.seed * 100_000 + i, f"i{i:03d}")
        (out / "instances" / f"{inst['instance_id']}.json").write_text(json.dumps(inst, indent=2))
        for e in inst["emails"]:
            flat.append(dict(instance_id=inst["instance_id"], **e))
            diff[e["label"]["difficulty"]] += 1
            scen[e["label"]["scenario"]] += 1
    with open(out / "emails.jsonl", "w") as f:
        for row in flat:
            f.write(json.dumps(row) + "\n")

    example = make_instance(args.seed, "ex", SMALL_CFG)
    (out / "example_small.json").write_text(json.dumps(example, indent=2))

    print(f"{args.instances} instances, {len(flat)} emails -> {out}/")
    print("difficulty:", dict(diff))
    print("scenario:  ", dict(scen))
    print(f"example_small.json: {len(example['matters'])} matters, {len(example['emails'])} emails")


if __name__ == "__main__":
    main()
