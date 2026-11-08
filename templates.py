"""Content library for the synthetic email generator.

Everything here is fictional. Slots in {braces} are filled by generate_data.py.

Role keys used in templates:
  user      - the lawyer whose mailbox this is
  assoc     - an associate at the user's firm staffed on the matter
  gc        - client's general counsel (shared across all matters for that client)
  client    - matter-specific client contact (e.g. CFO on a deal, CISO on a breach)
  opposing  - counsel on the other side (or agency staff attorney)
  cp        - counterparty principal (e.g. lead investor partner, forensic lead)
  third     - neutral / service third party (escrow agent, mediator, expert, ...)
"""

FIRST_NAMES = [
    "Aisha", "Ben", "Carla", "Daniel", "Elena", "Farid", "Grace", "Hiro", "Isabel", "James",
    "Kavya", "Liam", "Maya", "Nikhil", "Olivia", "Pedro", "Quinn", "Rachel", "Samuel", "Tara",
    "Umar", "Valerie", "Wei", "Ximena", "Yusuf", "Zoe", "Arjun", "Bianca", "Chen", "Diego",
    "Emma", "Femi", "Gabriel", "Hannah", "Ivan", "Jasmine", "Kenji", "Lucia", "Marcus", "Nadia",
    "Omar", "Priya", "Rafael", "Sofia", "Thomas", "Uma", "Victor", "Whitney", "Xavier", "Yara",
]
LAST_NAMES = [
    "Abbott", "Banerjee", "Castillo", "Dubois", "Eriksen", "Fischer", "Goldberg", "Haddad",
    "Ito", "Jensen", "Kowalski", "Lindqvist", "Mendoza", "Nakamura", "Okafor", "Patel",
    "Quintero", "Rosen", "Sato", "Thompson", "Underwood", "Varga", "Whitaker", "Xu", "Yamamoto",
    "Zhang", "Alvarez", "Brennan", "Chowdhury", "Delgado", "Ellis", "Ferreira", "Grant", "Huang",
    "Iyer", "Kaplan", "Laurent", "Moreau", "Novak", "Osei", "Park", "Reyes", "Shah", "Tanaka",
    "Vasquez", "Weiss", "Young", "Ziegler", "Morgan", "Lee",
]
CO_PREFIX = [
    "Northwind", "Halcyon", "Brightline", "Corvid", "Lumen", "Stratus", "Ironbridge", "Bluefin",
    "Cascade", "Vantage", "Evergreen", "Solace", "Pinnacle", "Redwood", "Quarry", "Tidewater",
    "Sterling", "Amberly", "Copperleaf", "Driftwood", "Keystone", "Lattice", "Mariner", "Nimbus",
    "Orchard", "Parallax", "Riverstone", "Silverpine", "Trellis", "Wavecrest",
]
CO_SUFFIX = [
    "Logistics", "Therapeutics", "Systems", "Foods", "Robotics", "Analytics", "Energy",
    "Health", "Software", "Materials", "Networks", "Biosciences", "Payments", "Labs",
]
CODENAMES = [
    "Falcon", "Bluebird", "Granite", "Juniper", "Atlas", "Meridian", "Kestrel", "Harbor",
    "Cobalt", "Sequoia", "Orion", "Tundra", "Saffron", "Larkspur",
]
STREETS = ["Market Street", "Mission Street", "Howard Street", "Embarcadero Center",
           "California Street", "Page Mill Road", "University Avenue", "Townsend Street"]
AGENCIES = [
    ("Federal Trade Commission", "FTC", "ftc.gov"),
    ("Securities and Exchange Commission", "SEC", "sec.gov"),
    ("Consumer Financial Protection Bureau", "CFPB", "cfpb.gov"),
    ("California Department of Justice", "California DOJ", "doj.ca.gov"),
]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
TIMES = ["9:00 a.m.", "10:30 a.m.", "noon", "2:00 p.m.", "3:30 p.m.", "5:00 p.m."]

# How orgs of each kind are named: (name template, domain suffix)
ORG_KINDS = {
    "company": ("{p} {s}", ".com"),
    "law_firm": ("{l1} & {l2} LLP", ".com"),
    "trust": ("{p} Trust Company", "trust.com"),
    "advisor": ("{p} Capital Advisors", "capital.com"),
    "fund": ("{p} Ventures", "vc.com"),
    "adr": ("{p} Dispute Resolution", "adr.com"),
    "consulting": ("{p} Technical Consulting", "tech.com"),
    "brokerage": ("{p} Commercial Realty", "realty.com"),
    "landlord": ("{p} Properties LLC", "properties.com"),
    "ediscovery": ("{p} Discovery", "discovery.com"),
    "forensics": ("{p} Cyber", "cyber.com"),
    "insurer": ("{p} Mutual Insurance", "mutual.com"),
    "court_reporting": ("{p} Court Reporting", "reporting.com"),
    "pr": ("{p} Communications", "comms.com"),
    "lender": ("{p} Bank", "bank.com"),
}

# --------------------------------------------------------------------------- #
# Matter types
# --------------------------------------------------------------------------- #
# Each matter type defines:
#   practice_area, name (matter name template), description
#   cp_kind      : what the counterparty is ("company", "fund", "person", "agency", ...)
#   opposing     : (org kind, title) for counsel on the other side, or None
#   cp_contact   : (title) if the counterparty principal emails directly, else None
#   client_title : title of the matter-specific client contact
#   third        : (role, org kind, title)
#   key_terms    : matter-specific identifiers (what intake would record)
#   keywords     : practice vocabulary (shared by all matters of this type)
#   ref / drift / status : short phrases used in cross-matter emails
#   openers      : thread-starting templates
#   new_sender   : template for an email from someone not yet in contacts

MATTER_TYPES = {
    "acquisition": dict(
        practice_area="M&A",
        name="{client_short} - Acquisition of {cp} (Project {code})",
        description="Buy-side acquisition of {cp} by {client}. Stock purchase, ~{amount}.",
        cp_kind="company",
        opposing=("law_firm", "Partner"),
        cp_contact=None,
        client_title="VP, Corporate Development",
        third=("escrow_agent", "trust", "Vice President, Escrow Services"),
        key_terms=["{mnum}", "Project {code}", "{code}", "{cp}", "{cp_short}"],
        keywords=["purchase agreement", "spa", "due diligence", "disclosure schedules", "escrow",
                  "earn-out", "hsr", "data room", "loi", "indemnification", "purchase price"],
        ref="Project {code}",
        drift="on Project {code}, the sellers are asking whether we've finished confirmatory diligence. Where are we?",
        status="Project {code}: seller comments on the SPA in; issues list circulated, signing targeted for {date}.",
        openers=[
            dict(frm="client", to=["user"], cc=["assoc"], subject="Project {code} - LOI countersigned",
                 body="Good news: {cp} countersigned the LOI this morning. We're targeting signing in roughly six weeks, so we'd like your team to start on the stock purchase agreement and get a diligence request list out. Their CFO expects the list by {day}.\n\nCan we do a kickoff call tomorrow?"),
            dict(frm="opposing", to=["user"], cc=["assoc"], subject="{cp_short} / {client_short} - SPA comments",
                 body="Attached is our markup of the SPA. The main open points are (1) the indemnification cap, which we have at 8% of the purchase price, (2) the survival period for fundamental reps, and (3) treatment of the {cp_short} customer contracts that require consent on a change of control.\n\nHappy to walk through on a call this week.",
                 attach=["{cp_short} SPA - Seller Comments.docx"]),
            dict(frm="user", to=["opposing"], cc=["assoc"], subject="Due diligence request list",
                 body="Please find attached our initial due diligence request list. We'd appreciate data room access for {assoc_first} and me as soon as it's set up. Priority items are the material contracts, IP assignments, and any pending litigation.",
                 attach=["Initial DD Request List.pdf"]),
            dict(frm="third", to=["user"], cc=[], subject="Escrow account opening - KYC documents",
                 body="To open the escrow account for the {code} transaction we will need KYC documentation for both buyer and seller, including certificates of good standing and beneficial ownership forms. The escrow amount in the current draft is {amount_small}. Who is our point of contact on the seller side?"),
            dict(frm="assoc", to=["user"], cc=[], subject="{code} - disclosure schedules open items",
                 body="I went through the latest disclosure schedules. Schedule 3.12 (material contracts) still omits two customer agreements we found in the data room, and Schedule 3.15 doesn't list the pending trademark opposition. Both are flagged in the issues list. Want me to raise these with {cp_short}'s counsel directly?"),
            dict(frm="client", to=["user"], cc=[], subject="Earn-out question from the board",
                 body="The board asked whether we could structure part of the {amount} purchase price as an earn-out tied to 2027 revenue. What are the main risks from our side, and is it too late to raise with the sellers?"),
            dict(frm="gc", to=["user"], cc=[], subject="HSR filing timing",
                 body="Do we need an HSR filing for this deal? If so, can we file before signing? I want to make sure the closing timeline in the board deck is realistic."),
        ],
        new_sender=dict(org="opposing", title="Associate", subject="Introduction - disclosure schedules",
                        body="I've joined the {cp_short} deal team and will be coordinating the disclosure schedules going forward. Please copy me on drafts of the SPA as well."),
    ),
    "financing": dict(
        practice_area="Emerging Companies / Venture",
        name="{client_short} - {round} Financing",
        description="{round} preferred stock financing for {client}, led by {cp}. Raising ~{amount}.",
        cp_kind="fund",
        opposing=("law_firm", "Partner"),
        cp_contact="Partner",
        client_title="Chief Executive Officer",
        third=("existing_investor", "fund", "Managing Director"),
        key_terms=["{mnum}", "{round}", "{cp}", "{cp_short}"],
        keywords=["term sheet", "pre-money", "cap table", "investors' rights", "voting agreement",
                  "preferred", "pro rata", "option pool", "closing"],
        ref="the {round}",
        drift="on the {round}, {cp_short} is asking about closing timing. Can you send them an update?",
        status="{round}: financing docs in negotiation with {cp_short}'s counsel; cap table reconciliation in progress.",
        openers=[
            dict(frm="client", to=["user"], cc=["gc"], subject="{round} term sheet from {cp}",
                 body="We received the attached term sheet from {cp} last night: {amount} at a {valuation} pre-money, 1x non-participating preferred, and a board seat for them. Can you take a look and flag anything off-market before I call them back on {day}?",
                 attach=["{cp_short} Term Sheet.pdf"]),
            dict(frm="opposing", to=["user"], cc=["assoc"], subject="{client_short} {round} - draft financing documents",
                 body="Attached please find drafts of the Stock Purchase Agreement, Investors' Rights Agreement and Voting Agreement for the {round}. Our client would like to sign by {date}. Please send the updated cap table and disclosure schedule when ready.",
                 attach=["SPA.docx", "IRA.docx", "Voting Agreement.docx"]),
            dict(frm="assoc", to=["user"], cc=[], subject="Cap table reconciliation",
                 body="I reconciled the cap table against the board consents. There's a 40,000-share discrepancy in the option pool from the 2024 grants. I'd like to fix this before we send the pro forma to the investors' counsel. Do you want to review first?"),
            dict(frm="cp", to=["user"], cc=["client"], subject="Closing timing",
                 body="Checking in on timing. Our investment committee approved the deal and we're ready to wire once the closing conditions are satisfied. Is {date} still realistic?"),
            dict(frm="user", to=["client"], cc=["assoc"], subject="Board and stockholder consents",
                 body="Attached are the board and stockholder consents approving the {round}. Please circulate for signature; we need a majority of the preferred to sign before closing.",
                 attach=["Board Consent.pdf", "Stockholder Consent.pdf"]),
            dict(frm="gc", to=["user"], cc=[], subject="Pro rata rights question",
                 body="One of our existing investors is asking whether they get to participate in this round. Can you check what their side letter says about pro rata rights?"),
        ],
        new_sender=dict(org="new:fund", title="Principal", subject="Participation in the {client_short} round",
                        body="We were introduced to {client_short} by {cp_short} and would like to take up to $2 million of the {round}. Who should we speak with about the subscription documents?"),
    ),
    "employment": dict(
        practice_area="Employment Litigation",
        name="{plaintiff} v. {client_short}",
        description="Wrongful termination and retaliation claims by former employee {plaintiff} against {client}. Case No. {case_no}.",
        cp_kind="person",
        opposing=("law_firm", "Partner"),
        cp_contact=None,
        client_title="Head of People",
        third=("mediator", "adr", "Mediator"),
        key_terms=["{mnum}", "{plaintiff}", "{plaintiff_last}", "{case_no}"],
        keywords=["wrongful termination", "retaliation", "litigation hold", "mediation", "deposition",
                  "personnel file", "complaint", "demand letter", "settlement"],
        ref="the {plaintiff_last} matter",
        drift="on the {plaintiff_last} matter, the mediator's office sent over dates. Can we lock one in?",
        status="{plaintiff_last}: complaint served; mediation being scheduled, deposition outline in draft.",
        openers=[
            dict(frm="client", to=["user"], cc=["gc"], subject="Demand letter - {plaintiff}",
                 body="We received the attached demand letter from counsel for {plaintiff}, who was terminated in August. The letter alleges wrongful termination and retaliation and demands {amount_small}. I've put a hold on the personnel file. How should we respond?",
                 attach=["Demand Letter.pdf"]),
            dict(frm="opposing", to=["user"], cc=[], subject="{plaintiff} v. {client_short} - Case No. {case_no}",
                 body="Please see attached the complaint filed today in {plaintiff} v. {client}, Case No. {case_no}. We are open to early mediation if your client is interested. Please confirm whether you will accept service on behalf of {client_short}.",
                 attach=["Complaint.pdf"]),
            dict(frm="user", to=["client"], cc=["assoc"], subject="Litigation hold notice",
                 body="Attached is a litigation hold notice for distribution to the custodians we discussed (the former manager, the HR business partner, and the regional director). Please have each of them acknowledge receipt. Nobody should delete emails, texts or Slack messages relating to the former employee.",
                 attach=["Litigation Hold Notice.docx"]),
            dict(frm="third", to=["user"], cc=["opposing"], subject="Mediation - available dates",
                 body="I have the following dates available for a full-day mediation: {date} and {date2}. Please send mediation briefs one week in advance. My fee schedule is attached.",
                 attach=["Fee Schedule.pdf"]),
            dict(frm="assoc", to=["user"], cc=[], subject="Deposition outline",
                 body="The draft outline for the plaintiff's deposition is in the folder. I focused on the 2025 performance reviews and the timing of the complaint to HR. Let me know if you want to add anything on damages."),
            dict(frm="gc", to=["user"], cc=[], subject="Settlement authority",
                 body="Before the call on {day}, can we talk about settlement authority? Leadership is open to resolving this but not at the number in the letter."),
        ],
        new_sender=dict(org="new:court_reporting", title="Scheduling Coordinator", subject="Deposition confirmation",
                        body="This confirms the deposition of {plaintiff} on {date} at 9:30 a.m. in Case No. {case_no}. A realtime feed and videographer have been requested. Please let us know of any changes."),
    ),
    "patent": dict(
        practice_area="IP Litigation",
        name="{client_short} v. {cp_short} ('{patent_short} Patent)",
        description="Patent infringement suit by {client} against {cp} asserting U.S. Patent No. {patent}.",
        cp_kind="company",
        opposing=("law_firm", "Partner"),
        cp_contact=None,
        client_title="Chief Technology Officer",
        third=("technical_expert", "consulting", "Principal"),
        key_terms=["{mnum}", "{patent}", "'{patent_short}", "{cp}", "{cp_short}"],
        keywords=["infringement", "claim construction", "prior art", "protective order", "claims",
                  "contentions", "expert", "patent"],
        ref="the '{patent_short} patent case",
        drift="on the '{patent_short} patent case, our CTO wants to know if we should expect a counterclaim.",
        status="'{patent_short} patent: protective order negotiated; infringement contentions due {date}.",
        openers=[
            dict(frm="client", to=["user"], cc=["gc"], subject="{cp} product launch - possible infringement of '{patent_short} patent",
                 body="Our engineers looked at the product {cp} launched last month and believe it practices claims 1 and 7 of our '{patent_short} patent. Teardown notes attached. Can we discuss options, including a cease-and-desist letter?",
                 attach=["Teardown Notes.pdf"]),
            dict(frm="opposing", to=["user"], cc=["assoc"], subject="{client_short} v. {cp_short} - proposed protective order",
                 body="Attached is our proposed stipulated protective order. We've included a two-tier designation and a prosecution bar. Let us know if your client can agree by {day}.",
                 attach=["Proposed Protective Order.docx"]),
            dict(frm="third", to=["user"], cc=["assoc"], subject="Claim construction - preliminary views",
                 body="Having reviewed the specification, I think 'adaptive sampling interval' is the critical term. Under its plain meaning the accused device likely meets it. I'll have a draft declaration to you by {date}."),
            dict(frm="assoc", to=["user"], cc=[], subject="Prior art search results",
                 body="The prior art search came back. Two references are worth a look: a 2014 IEEE paper and a 2016 Japanese publication. Neither discloses the feedback loop in claim 1, but the Japanese reference comes close on claim 7. Summary attached.",
                 attach=["Prior Art Summary.pdf"]),
            dict(frm="user", to=["client"], cc=["assoc"], subject="Infringement contentions due {date}",
                 body="Reminder that our infringement contentions are due {date}. We need the source code review scheduled and your engineers' availability for claim charts next week."),
            dict(frm="gc", to=["user"], cc=[], subject="Budget through trial",
                 body="Finance asked for a litigation budget through trial. Can you send something by the end of the month? Rough numbers are fine."),
        ],
        new_sender=dict(org="new:consulting", title="Senior Engineer", subject="Engagement - source code review",
                        body="Following up on the call with {assoc_first}: we can start the source code review for the '{patent_short} patent matter on {date}. Our conflicts check against {cp} came back clear. Engagement letter attached."),
    ),
    "lease": dict(
        practice_area="Real Estate",
        name="{client_short} - Headquarters Lease ({address})",
        description="Office lease negotiation for {client}'s new headquarters at {address}, landlord {cp}.",
        cp_kind="landlord",
        opposing=("law_firm", "Partner"),
        cp_contact=None,
        client_title="Director of Real Estate",
        third=("broker", "brokerage", "Senior Vice President"),
        key_terms=["{mnum}", "{address}", "{cp}"],
        keywords=["lease", "rsf", "ti allowance", "rent commencement", "snda", "estoppel",
                  "landlord", "tenant", "operating expense", "loi"],
        ref="the {address} lease",
        drift="on the {address} lease, the broker says the landlord moved on TI. Did you see that?",
        status="{address}: second turn of landlord's lease draft; SNDA requested from lender.",
        openers=[
            dict(frm="client", to=["user"], cc=[], subject="Lease LOI - {address}",
                 body="We've agreed on a non-binding LOI with {cp} for about 42,000 RSF at {address}: 10-year term, $68/RSF with 3% annual bumps, and a TI allowance of $95/RSF. Can you start reviewing the landlord's form lease?",
                 attach=["Signed LOI.pdf"]),
            dict(frm="opposing", to=["user"], cc=[], subject="{address} - lease draft",
                 body="Attached is the landlord's draft lease. Please note the landlord does not agree to the co-tenancy provision raised in the LOI.",
                 attach=["Office Lease - Landlord Draft.docx"]),
            dict(frm="third", to=["user"], cc=["client"], subject="TI allowance and rent commencement",
                 body="Quick update from the landlord's side: they'll go to $100/RSF TI if we accept rent commencement 120 days after delivery instead of 180. Thoughts before I respond?"),
            dict(frm="user", to=["opposing"], cc=["assoc"], subject="SNDA and estoppel",
                 body="We'll need an SNDA from the landlord's lender as a condition to lease effectiveness. Please confirm who the lender is and whether they have a standard form."),
            dict(frm="assoc", to=["user"], cc=[], subject="Lease abstract",
                 body="The lease abstract for the current draft is attached. Biggest open issues: the operating expense cap, assignment rights on a change of control, and restoration obligations at the end of the term.",
                 attach=["Lease Abstract.xlsx"]),
            dict(frm="gc", to=["user"], cc=[], subject="Signing authority",
                 body="Who needs to sign on our side? Our CFO is out next week."),
        ],
        new_sender=dict(org="new:lender", title="Loan Officer", subject="SNDA request",
                        body="We received a request for an SNDA in favor of {client}. Our standard form is attached; we generally do not accept tenant revisions beyond the notice provisions."),
    ),
    "regulatory": dict(
        practice_area="Regulatory / Investigations",
        name="{client_short} - {cp_short} Investigation (CID No. {cid})",
        description="Response to {cp} civil investigative demand regarding {client}'s customer data practices.",
        cp_kind="agency",
        opposing=("agency", "Staff Attorney"),
        cp_contact=None,
        client_title="Chief Compliance Officer",
        third=("ediscovery_vendor", "ediscovery", "Project Manager"),
        key_terms=["{mnum}", "{cid}", "{cp}"],
        keywords=["civil investigative demand", "cid", "production", "custodians", "privilege log",
                  "meet and confer", "specifications", "investigation"],
        ref="the {cp_short} investigation",
        drift="on the {cp_short} investigation, the audit committee wants to know whether we're on track for the first production.",
        status="{cp_short} CID: collection 80% complete; first rolling production targeted for {date}.",
        openers=[
            dict(frm="gc", to=["user"], cc=["client"], subject="Civil investigative demand received",
                 body="We received a Civil Investigative Demand from the {cp} this morning (CID No. {cid}). It asks for documents about our customer data practices going back to 2021. The return date is {date}. Can you call me?",
                 attach=["CID.pdf"]),
            dict(frm="opposing", to=["user"], cc=[], subject="CID No. {cid} - meet and confer",
                 body="Following up on your letter. Staff is willing to discuss narrowing Specifications 4 and 7 but expects a rolling production to begin within 30 days. Please propose dates for a meet and confer."),
            dict(frm="third", to=["user"], cc=["assoc"], subject="Collection status - 14 custodians",
                 body="We completed collection for 11 of 14 custodians. Total volume is about 1.8 TB before deduplication. Three custodians have mobile devices we still need to image. Processing estimate attached.",
                 attach=["Processing Estimate.pdf"]),
            dict(frm="assoc", to=["user"], cc=[], subject="Privilege log - first production",
                 body="The draft privilege log for the first production is attached (312 entries). I want to discuss how we're treating emails with the outside privacy consultant before we send it to staff.",
                 attach=["Privilege Log v1.xlsx"]),
            dict(frm="user", to=["client"], cc=["assoc"], subject="Custodian interviews next week",
                 body="We'd like to interview the product and data engineering leads next week. Each interview should take about 90 minutes. Please remind them that the interviews are privileged and confidential."),
            dict(frm="client", to=["user"], cc=[], subject="Audit committee update",
                 body="The audit committee wants an update at its meeting on {date}. Could you prepare a short summary of status, exposure, and next steps?"),
        ],
        new_sender=dict(org="opposing", title="Investigator", subject="Production format",
                        body="I'm working with the staff attorney on this matter. Please confirm that productions will follow the agency's technical specifications for load files. A copy is attached."),
    ),
    "contract": dict(
        practice_area="Commercial Litigation",
        name="{client_short} v. {cp_short} (MSA Dispute)",
        description="Breach of master services agreement claims by {client} against vendor {cp}.",
        cp_kind="company",
        opposing=("law_firm", "Partner"),
        cp_contact=None,
        client_title="Chief Operating Officer",
        third=("arbitration_admin", "adr", "Case Administrator"),
        key_terms=["{mnum}", "{cp}", "{cp_short}"],
        keywords=["master services agreement", "msa", "breach", "cure", "sla", "arbitration",
                  "limitation of liability", "damages", "service credits"],
        ref="the {cp_short} dispute",
        drift="on the {cp_short} dispute, their account team reached out to our COO again.",
        status="{cp_short} MSA: notice of breach sent, cure period running; damages model in draft.",
        openers=[
            dict(frm="client", to=["user"], cc=["gc"], subject="{cp} - repeated SLA failures",
                 body="{cp} has missed the uptime SLA under our master services agreement for three straight months, and their latest outage took down order processing for two days. We want to send a formal notice of breach. The MSA is attached.",
                 attach=["MSA.pdf"]),
            dict(frm="user", to=["opposing"], cc=["assoc"], subject="Notice of breach - Master Services Agreement",
                 body="Please see the attached notice of material breach under Section 11.2 of the Master Services Agreement between our clients. Under Section 11.3, your client has 30 days to cure.",
                 attach=["Notice of Breach.pdf"]),
            dict(frm="opposing", to=["user"], cc=[], subject="Response to notice of breach",
                 body="We disagree that the outages constitute a material breach. Most of the downtime was caused by your client's own configuration changes. Our client is nevertheless willing to discuss service credits without prejudice."),
            dict(frm="third", to=["user"], cc=["opposing"], subject="Demand for arbitration - administrative conference",
                 body="This confirms receipt of the demand for arbitration in {client} v. {cp}. The administrative conference is scheduled for {date}. Please confirm your availability."),
            dict(frm="assoc", to=["user"], cc=[], subject="Damages model",
                 body="First cut at the damages model: lost revenue during the outages is roughly {amount_small}, plus cover costs for the replacement vendor. The limitation of liability clause may cap us at 12 months of fees unless we can show gross negligence.",
                 attach=["Damages Model v1.xlsx"]),
            dict(frm="gc", to=["user"], cc=[], subject="They called our COO",
                 body="They called our COO directly and floated a settlement. I told them everything goes through counsel. Can you follow up with their lawyers?"),
        ],
        new_sender=dict(org="new:company", title="Implementation Manager", subject="Transition planning",
                        body="We've been engaged by {client_short} to replace {cp} as the platform vendor. Their team suggested we coordinate with you on what transition data we can request from {cp_short} under the MSA."),
    ),
    "breach": dict(
        practice_area="Privacy & Cybersecurity",
        name="{client_short} - Data Security Incident",
        description="Privileged incident response for unauthorized access to {client}'s customer database. Forensics by {cp}.",
        cp_kind="forensics",
        opposing=None,
        cp_contact="Incident Response Lead",
        client_title="Chief Information Security Officer",
        third=("insurer", "insurer", "Claims Specialist"),
        key_terms=["{mnum}", "{cp}", "{cp_short}"],
        keywords=["incident", "forensic", "unauthorized access", "exfiltrated", "notification",
                  "attorneys general", "cyber policy", "affected individuals", "breach"],
        ref="the security incident",
        drift="on the security incident, our insurer is asking for an updated budget.",
        status="Security incident: forensics report pending; consumer notification letters in draft.",
        openers=[
            dict(frm="client", to=["user"], cc=["gc"], subject="URGENT - security incident",
                 body="We detected unauthorized access to our customer database last night. It's contained, and we've engaged {cp} for forensics. We'd like you to direct the investigation so it's covered by privilege. Can you join a call at {time}?"),
            dict(frm="cp", to=["user"], cc=["client"], subject="Preliminary forensic findings",
                 body="Per your direction, attached are preliminary findings. Initial access was through a compromised VPN credential; the attacker exfiltrated roughly 220,000 records containing names, emails and hashed passwords. Our final report will follow.",
                 attach=["Preliminary Findings - PRIVILEGED.pdf"]),
            dict(frm="third", to=["user"], cc=[], subject="Cyber claim - panel counsel approval",
                 body="We've opened a claim under the cyber policy. Please send your rates for panel approval and an initial budget. Note the policy requires our consent before engaging vendors other than {cp_short}."),
            dict(frm="assoc", to=["user"], cc=[], subject="State notification deadlines",
                 body="I mapped affected individuals by state. The tightest deadlines are 30 days in Colorado and Washington. Draft consumer notification letter attached for your review.",
                 attach=["Notification Letter Draft.docx"]),
            dict(frm="user", to=["client"], cc=["gc"], subject="Regulator notifications",
                 body="Given the number of affected residents, we'll need to notify several state attorneys general. I'd recommend holding off on any public statement until we've finalized scope with {cp_short}."),
            dict(frm="gc", to=["user"], cc=[], subject="Customer contracts - notice obligations",
                 body="Some enterprise customers have contractual notice requirements of 72 hours. Can your team review the top 20 customer agreements today?"),
        ],
        new_sender=dict(org="new:pr", title="Managing Director", subject="Communications support",
                        body="{client_short}'s CEO asked us to help with external communications around the incident. Could we get 30 minutes with you to align on what can be said publicly?"),
    ),
}

# --------------------------------------------------------------------------- #
# Content that is NOT matter-specific
# --------------------------------------------------------------------------- #

# Short replies used inside threads. Content-light on purpose: the thread is the signal.
REPLIES = [
    "Thanks. Received; we'll review and come back to you by {day}.",
    "Works for me. Let's do {day} at {time}.",
    "Agreed on the approach. Please go ahead and circulate the revised draft.",
    "Adding {assoc_first}, who will handle the day-to-day on this.",
    "Quick follow-up on the below. Any update?",
    "See my comments inline. The main issue is still timing; otherwise fine.",
    "Confirmed. I'll update the checklist.",
    "Thanks for the quick turnaround. Let me check with the team and revert.",
    "Can we push this to next week? Things are busy on our end.",
    "Understood. I'll send a marked version tonight.",
]

# Standalone emails with no matter-specific content. Truth = matter the sender is on,
# but often genuinely unknowable from the text.
GENERIC = [
    dict(frm="gc", subject="Quick call?",
         body="Do you have 15 minutes this afternoon? I want to run something by you before my meeting with the leadership team."),
    dict(frm="gc", subject="Following up",
         body="Any update on where things stand? Our CEO asked me this morning."),
    dict(frm="client", subject="Checking in",
         body="Is there anything you need from us this week? I'm traveling Thursday and Friday."),
    dict(frm="assoc", subject="Drafts for your review",
         body="I uploaded the revised drafts to the DMS. Let me know if you'd like me to turn your comments tonight."),
    dict(frm="opposing", subject="Call next week",
         body="Are you available next week to discuss the open issues? Tuesday or Wednesday afternoon works for us."),
    dict(frm="gc", subject="Invoice question",
         body="Got your latest invoice. Can you break out the time entries by workstream? Finance needs it for accruals."),
]

DRIFT_LEAD = "Thanks. Separately, {drift}"

NO_MATTER = [
    dict(org="internal", title="Marketing Coordinator", subject="Firm Weekly: new partners and office updates",
         body="This week: we welcome three new lateral partners, the 4th floor kitchen reopens Monday, and holiday party RSVPs are due Friday.", trap=None),
    dict(org="internal", title="Professional Development Manager", subject="CLE reminder: credits due by December 31",
         body="Our records show you still need 3 ethics credits this compliance period. On-demand programs are available on the firm intranet.", trap=None),
    dict(org="internal", title="IT Service Desk", subject="Scheduled maintenance this Saturday",
         body="The document management system will be unavailable Saturday from 8 a.m. to noon for upgrades. Please save your work and log out Friday evening.", trap=None),
    dict(org="new:pr", title="Editor", subject="Deal Digest: earn-outs, escrows and purchase price adjustments in 2026",
         body="In this issue: why earn-out disputes are rising, market data on escrow sizes and indemnification caps, and what buyers are asking for in due diligence on AI companies.", trap="acquisition"),
    dict(org="new:adr", title="Section Chair", subject="Employment Law Section luncheon",
         body="Join us for a panel on retaliation claims and wrongful termination trends, plus practical tips on mediation and deposition strategy. Lunch provided.", trap="employment"),
    dict(org="internal", title="Partner", subject="Lunch Thursday?",
         body="Are you free for lunch Thursday? Want to catch up on the associate review process."),
    dict(org="new:company", title="Recruiter", subject="Confidential opportunity",
         body="I'm working with a leading in-house legal team looking for a deputy general counsel. Would you be open to a confidential conversation?", trap=None),
]
