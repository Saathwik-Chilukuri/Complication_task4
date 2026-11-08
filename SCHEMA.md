# Synthetic data schema

`python generate_data.py [--instances 50] [--seed 7] [--out data]` writes:

| file | contents |
|---|---|
| `data/instances/iNNN.json` | one **instance** = one lawyer's workspace in the app |
| `data/emails.jsonl` | every email from every instance, one per line, with `instance_id` (handy for pandas) |
| `data/example_small.json` | 3 matters, ~12 emails, one client shared by two matters (the assignment's toy example) |

Output is deterministic for a given seed. Everything is fictional.

## Instance

```jsonc
{
  "instance_id": "i007",
  "seed": 700007,
  "firm": {"name": "Okafor & Jensen LLP", "domain": "okaforjensen.com"},
  "user_contact_id": "i007-c000",   // mailbox owner; on every email
  "matters":  [Matter],
  "contacts": [Contact],
  "emails":   [Email]               // sorted by timestamp
}
```

Classification happens **within** an instance: candidate labels are that instance's
`matters` plus "no matter" (`primary_matter_id: null`).

## Matter (what the app knows from matter intake)

```jsonc
{
  "matter_id": "i007-m02",
  "matter_number": "83972-002",            // <client no>-<seq>; same prefix for the same client
  "name": "Nimbus - Headquarters Lease (1939 University Avenue)",
  "client": "Nimbus Therapeutics",
  "matter_type": "lease",                  // acquisition | financing | employment | patent | lease | regulatory | contract | breach
  "practice_area": "Real Estate",
  "description": "...",
  "counterparty": "Keystone Properties LLC",
  "opposing_counsel_firm": "Underwood & Jensen LLP",   // null if none (e.g. breach response)
  "status": "open",
  "opened_on": "2026-06-14",
  "key_terms": ["83972-002", "1939 University Avenue", "Keystone Properties LLC"],  // matter-unique identifiers
  "contacts": [{"contact_id": "i007-c004", "role": "client_general_counsel"}, ...]
}
```

Contact roles: `client_general_counsel`, `client_contact`, `internal_team`, `opposing_counsel`,
`counterparty`, plus one type-specific third party (`escrow_agent`, `mediator`, `technical_expert`,
`broker`, `ediscovery_vendor`, `arbitration_admin`, `insurer`, `existing_investor`).
The mailbox owner is implicitly on every matter and is not listed.

## Contact

```jsonc
{"contact_id": "i007-c004", "name": "Daniel Osei", "first": "Daniel",
 "email": "daniel.osei@nimbusther.com", "organization": "Nimbus Therapeutics",
 "org_type": "company", "title": "General Counsel", "is_internal": false}
```

`contacts` also includes people **not** linked to any matter (new senders, newsletter senders,
firm billing/IT), the way an address book would.

## Email

```jsonc
{
  "email_id": "i007-e012", "thread_id": "i007-t004",
  "in_reply_to": "i007-e009",          // null for thread starters
  "references": ["i007-e005", "i007-e009"],
  "timestamp": "2026-07-21T14:05:00", "folder": "inbox",   // or "sent"
  "from": {"name": "...", "email": "..."}, "to": [...], "cc": [...],
  "subject": "Re: Signing authority",
  "body": "greeting\n\ntext\n\nsignature\n\nOn ..., X wrote:\n> quoted parent",
  "attachments": ["Office Lease - Landlord Draft.docx"],
  "split": "history",                  // first 60% by time = "history" (already filed), rest = "incoming"
  "label": { ... }                     // GROUND TRUTH + DIAGNOSTICS: never feed to a model
}
```

`split` is there for your prior: estimate P(M | metadata) from `history`, evaluate on `incoming`.

### label

```jsonc
{
  "primary_matter_id": "i007-m02",     // null = belongs to no matter
  "matter_ids": ["i007-m02", "i007-m00"],   // all relevant matters (len > 1 for multi-matter emails)
  "scenario": "topic_drift",           // how it was generated (below)
  "difficulty": "ambiguous",           // obvious | moderate | ambiguous (rule below)
  "ambiguity_reasons": ["thread_topic_changed", "participants_span_multiple_matters"],
  "signals": {
    "participant_candidates": [...],   // matters whose known contacts best overlap from/to/cc (domain fallback)
    "thread_candidates": [...],        // parent email's matters; null if thread starter
    "identifier_candidates": [...],    // matters whose key_terms appear in subject/body
    "keyword_candidates": [...],       // matters whose practice keywords appear >= 2 times
    "metadata_points_to_truth": true,  // (thread if reply else participants) == truth
    "text_points_to_truth": false      // (identifiers, else keywords) == truth
  }
}
```

**Difficulty rule:** `obvious` = metadata and text both point exactly at the truth;
`moderate` = only one does; `ambiguous` = neither does, or the email spans several matters.
This lines up with the two-stage model: `obvious`/meta-clear emails should be settled by
P(M | X_meta); the rest need the semantic stage.

### Scenarios

| scenario | what it models |
|---|---|
| `matter_thread` | thread opener from a matter template (client, opposing counsel, third party, associate, or GC) |
| `thread_reply` | short reply-all ("Works for me, Thursday at 2"); the thread is the main signal |
| `generic_content` | "Quick call?" / "Following up" from someone on the matter; no matter-specific text |
| `new_sender` | sender not in contacts (court reporter, lender, new associate at opposing firm...) |
| `multi_matter` | shared-client GC asks about two matters in one email |
| `multi_matter_status` | associate's weekly status covering all their matters |
| `topic_drift` | reply in matter A's thread whose new content is about matter B (primary = B) |
| `billing` / `billing_multi` | firm billing lists a client's matter numbers (content-only signal) |
| `no_matter` | firm newsletter, IT, CLE, recruiter |
| `no_matter_keyword_trap` | industry newsletter full of M&A or employment keywords |

### Ambiguity sources built into each instance (configurable in `DEFAULT_CFG`)

- **Shared client** (p=0.6): one client has two matters, and their GC is on both.
- **Shared opposing counsel** (p=0.4): two matters face the same law firm, sometimes the same lawyer.
- **Duplicate practice type** (p=0.2): e.g. two financings, so the vocabulary overlaps.
- **Internal staff** are on several matters, so associate emails carry weak metadata.
- **Reply quoting** (p=0.75): replies sometimes quote the parent and sometimes don't.
