"""
risks.py

Rule-based legal risk analysis.

Two kinds of findings:
    - "Risky wording":      a sentence matches a known risky pattern
                            (unlimited liability, unilateral changes, auto-renewal, ...)
    - "Missing protection": an important clause type is absent from the contract
                            (no limitation of liability, no governing law, ...)

Every finding has a severity (High / Medium / Low), a short explanation of why it
is risky and a suggested mitigation. An overall 0-100 risk score is derived from
the severities.

This is a screening aid, not legal advice.
"""

import re

from clauses import segment_clauses, extract_clauses
from obligations import split_sentences

SEVERITY_WEIGHT = {"High": 12, "Medium": 6, "Low": 2}
SEVERITY_ORDER = {"High": 0, "Medium": 1, "Low": 2}

# (id, category, severity, title, pattern, why, recommendation)
RISK_RULES = [
    ("unlimited_liability", "Liability", "High", "Unlimited liability",
     r"unlimited liability|liability (?:shall|will) not be (?:limited|capped)|"
     r"without (?:any )?(?:limit|limitation|cap)\b|no (?:limit|cap) on (?:its |the )?liability",
     "Exposure is not capped, so one claim could exceed the value of the contract.",
     "Negotiate a liability cap, usually tied to fees paid in the last 12 months."),

    ("broad_indemnity", "Liability", "High", "Broad indemnification",
     r"indemnif\w+[^.]{0,120}\b(?:any and all|all)\b[^.]{0,40}\b(?:losses|claims|damages|liabilit\w+|costs|expenses)|"
     r"indemnif\w+[^.]{0,80}\bwhether or not\b|"
     r"indemnif\w+[^.]{0,120}\b(?:arising (?:out of|from)[^.]{0,40})?negligence of (?:the )?(?:indemnitee|other party)",
     "A wide indemnity can make you pay for losses you did not cause, possibly including the other side's own negligence.",
     "Limit the indemnity to third-party claims caused by your breach or negligence, and make it mutual."),

    ("consequential_damages", "Liability", "Medium", "Liability for consequential damages",
     r"(?:including|including without limitation|including but not limited to)[^.]{0,40}(?:consequential|indirect|special|punitive) damages|"
     r"(?:liable|responsible) for[^.]{0,40}(?:consequential|indirect|special|punitive)",
     "Liability extends to indirect losses such as lost profits, which are hard to predict and can be very large.",
     "Exclude consequential, indirect and punitive damages for both parties."),

    ("personal_guarantee", "Financial", "High", "Personal guarantee",
     r"personal(?:ly)? guarant\w+|guarantee[^.]{0,40}personal(?:ly)?|jointly and severally",
     "Individuals can be held personally responsible for the company's obligations.",
     "Avoid personal guarantees, or cap them in amount and duration."),

    ("unilateral_change", "Fairness", "High", "One party can change terms unilaterally",
     r"(?:may|can|reserves? the right to|shall have the right to)\s+(?:\w+\s+){0,3}(?:modify|amend|change|alter|revise|update)[^.]{0,80}"
     r"(?:at any time|from time to time|without (?:prior )?(?:notice|consent)|sole discretion|in its discretion)",
     "The other party can rewrite the deal after signing, and you may be bound without agreeing.",
     "Require changes to be in writing and signed by both parties, or give notice and a right to terminate."),

    ("sole_discretion", "Fairness", "Medium", "Sole or absolute discretion",
     r"sole (?:and absolute )?discretion|absolute discretion|sole judg(?:e)?ment",
     "A decision is left entirely to one party with no standard it must meet.",
     "Replace with 'reasonable discretion' or add objective criteria."),

    ("termination_convenience", "Termination", "Medium", "Termination without cause",
     r"terminat\w+[^.]{0,80}(?:without cause|for convenience|at any time for any reason|for any or no reason)|"
     r"(?:without cause|for convenience)[^.]{0,60}terminat\w+",
     "The other side can walk away at any time, leaving you with sunk costs.",
     "Make termination for convenience mutual, require a long notice period, and cover wind-down costs."),

    ("immediate_termination", "Termination", "Medium", "Immediate termination right",
     r"terminat\w+[^.]{0,60}(?:immediately|with immediate effect|forthwith)[^.]{0,80}(?:without|no)\s+(?:prior\s+)?(?:notice|cure|opportunity)|"
     r"terminat\w+[^.]{0,40}(?:without (?:prior )?notice)",
     "The contract can end instantly with no chance to fix a problem.",
     "Add a written notice and a cure period (for example 30 days) before termination for breach."),

    ("auto_renewal", "Term & Renewal", "Medium", "Automatic renewal",
     r"auto(?:matic(?:ally)?)?[- ]?renew\w*|renew\w*\s+automatically|automatically\s+(?:be\s+)?(?:extended|renewed)|"
     r"shall (?:be )?(?:deemed )?(?:renewed|extended) (?:for|unless)",
     "You may be locked into another term if you miss the cancellation window.",
     "Calendar the non-renewal notice date, or change to renewal by mutual written agreement."),

    ("perpetual_irrevocable", "Term & Renewal", "Medium", "Perpetual or irrevocable commitment",
     r"\birrevocabl[ey]\b|\bin perpetuity\b|\bperpetual(?:ly)?\b",
     "An open-ended commitment that cannot be undone, even if circumstances change.",
     "Set a fixed duration or add a termination path."),

    ("broad_ip_assignment", "Intellectual Property", "High", "Broad IP assignment or licence",
     r"assigns?[^.]{0,60}all (?:right|rights|title|interest)[^.]{0,80}(?:intellectual property|work product|deliverables|inventions)|"
     r"work made for hire|"
     r"(?:perpetual|irrevocable|worldwide|royalty[- ]free)[^.]{0,60}licen[sc]e[^.]{0,80}(?:sublicens|transfer)|"
     r"(?:all|any) (?:intellectual property|inventions)[^.]{0,60}(?:whether or not|including (?:pre-existing|background))",
     "You may give up ownership of your existing or future IP, including work unrelated to this project.",
     "Limit the assignment to project deliverables, keep pre-existing IP, and grant a licence rather than ownership where possible."),

    ("non_compete", "Restrictive Covenants", "High", "Non-compete / exclusivity",
     r"non-?compet\w+|shall not (?:directly or indirectly )?compete|"
     r"shall not (?:directly or indirectly )?(?:engage|carry on)[^.]{0,80}(?:business|competing)|"
     r"(?<!non-)exclusiv(?:e|ity)[^.]{0,40}(?:supplier|provider|dealer|basis|arrangement)",
     "Restricts your ability to work with others or run your own business. Enforceability varies by jurisdiction.",
     "Narrow the scope, geography and duration, or remove it."),

    ("non_solicit", "Restrictive Covenants", "Low", "Non-solicitation",
     r"non-?solicit\w*|shall not[^.]{0,60}(?:solicit|hire|employ)[^.]{0,60}(?:employees|personnel|customers|clients)",
     "Limits hiring or contacting the other side's people or customers.",
     "Keep it mutual, short (6-12 months) and limited to staff you worked with directly."),

    ("penalties", "Financial", "Medium", "Penalties or liquidated damages",
     r"liquidated damages|\bpenalt(?:y|ies)\b|forfeit\w*|\bsurcharge\b|\bliquidated sum",
     "Fixed charges apply on breach, whatever the actual loss. Courts may refuse to enforce penalty clauses.",
     "Confirm the amount is a genuine pre-estimate of loss and subject to a cap."),

    ("late_interest", "Financial", "Medium", "High late-payment interest",
     r"(?:interest|late (?:fee|charge))[^.]{0,80}\b(?:1\.5|[2-9]|\d{2,})(?:\.\d+)?\s?%\s*(?:per|a|each|/)\s*(?:month|mo)\b|"
     r"(?:interest|late (?:fee|charge))[^.]{0,80}\b(?:[2-9]\d|\d{3,})(?:\.\d+)?\s?%\s*(?:per|a|each|/)?\s*(?:annum|year)?",
     "Interest at this rate compounds into a large annual cost on late invoices.",
     "Cap interest at a reasonable annual rate (for example 8-12%) and add a grace period."),

    ("short_deadline", "Financial", "Medium", "Very short deadlines",
     r"within\s+(?:\w+\s+)?\(?(?:1|2|3|4|5|one|two|three|four|five|24|48|72)\)?\s*(?:\(\d+\)\s*)?(?:hours?|business days?|days?)\b",
     "A tight deadline is easy to miss and can trigger breach, penalties or termination.",
     "Check you can meet it, or negotiate a longer period (usually 15-30 days)."),

    ("warranty_disclaimer", "Warranties", "Medium", "Warranty disclaimer",
     r"\bas[- ]is\b|disclaims? all (?:other )?(?:express or implied )?warrant\w+|no warrant(?:y|ies) (?:of any kind|whatsoever)|"
     r"without (?:any )?warrant\w+",
     "No guarantee of quality or fitness; you carry the risk if the product or service fails.",
     "Ask for basic warranties on quality, conformity with specifications and non-infringement."),

    ("liability_exclusion", "Liability", "Medium", "Broad exclusion of liability",
     r"(?:shall|will) (?:in no event|under no circumstances) be liable|"
     r"(?:excludes?|disclaims?) (?:all|any) liability|"
     r"(?:shall|will) not be (?:liable|responsible) for any (?:loss|damage|claim)",
     "One side avoids responsibility for almost everything, so you may have no remedy.",
     "Make the exclusion mutual and carve out gross negligence, fraud and breach of confidentiality."),

    ("waiver_of_rights", "Fairness", "Medium", "Waiver of rights",
     r"(?:irrevocably |hereby |expressly )?waives?[^.]{0,60}\b(?:right|rights|claim|claims|remed\w+|defen[cs]es?|jury)\b",
     "You may give up legal remedies you would otherwise have.",
     "Remove the waiver or limit it to specific, named rights."),

    ("class_waiver_arbitration", "Dispute Resolution", "Medium", "Mandatory arbitration / class waiver",
     r"(?:binding|mandatory|final) arbitration|class action waiver|waive[^.]{0,40}class action|"
     r"(?:shall|must) be (?:finally )?(?:settled|resolved)[^.]{0,40}by arbitration",
     "Disputes are decided privately with limited appeal rights, and group claims may be barred.",
     "Check the seat, rules and cost allocation of the arbitration, and keep access to court for urgent relief."),

    ("exclusive_jurisdiction", "Dispute Resolution", "Low", "Exclusive jurisdiction",
     r"exclusive jurisdiction|submit(?:s)? to the exclusive|courts? of [A-Z][\w ,]{2,40} (?:shall have )?exclusive",
     "You may need to litigate in a distant or unfamiliar court.",
     "Prefer your home jurisdiction or a neutral venue."),

    ("assignment_without_consent", "Assignment", "Medium", "Assignment without consent",
     r"(?:may|shall have the right to|can)\s+assign[^.]{0,80}without (?:the )?(?:prior )?(?:written )?(?:consent|approval|notice)|"
     r"assign[^.]{0,40}(?:to any (?:third )?party|to an affiliate)[^.]{0,40}without",
     "The other party can transfer the contract to someone you did not choose.",
     "Require your consent for assignment, or at least notice and a right to terminate."),

    ("best_efforts", "Vague Terms", "Medium", "Best efforts standard",
     r"\bbest efforts\b|\bbest endeavou?rs\b|\ball reasonable efforts\b",
     "Courts may read this as requiring you to go far beyond what is commercially reasonable.",
     "Use 'commercially reasonable efforts' and define what is expected."),

    ("vague_terms", "Vague Terms", "Low", "Vague or subjective wording",
     r"\bas (?:determined|deemed (?:necessary|appropriate)) by\b|\bsatisfactory to\b|\bfrom time to time\b|"
     r"\bsuch other (?:terms|conditions)\b|\band such other\b|\bor as otherwise (?:required|determined)\b",
     "Open-ended wording leaves room for disagreement about what is required.",
     "Replace with specific criteria, amounts or timeframes."),

    ("incomplete_terms", "Drafting", "Medium", "Blank or undetermined terms",
     r"\[\s*\]|_{3,}|\bTBD\b|\bTBC\b|to be (?:agreed|determined|decided|negotiated|confirmed)\b|\bagreement to agree\b|\bINSERT\b",
     "Placeholders or terms to be agreed later may make that part of the contract unenforceable.",
     "Fill in the blanks or define how the term will be set (formula, third-party expert, default)."),

    ("data_sharing", "Data & Privacy", "Medium", "Broad data use or sharing",
     r"(?:sell|share|disclose|transfer)[^.]{0,60}(?:personal (?:data|information)|customer data|user data)[^.]{0,60}(?:third part\w+|affiliates|any (?:person|party))|"
     r"(?:use|process)[^.]{0,40}(?:data|information)[^.]{0,40}(?:for any (?:purpose|reason)|for its own purposes)",
     "Data may be used or passed on in ways you did not expect, with privacy-law consequences.",
     "Limit data use to performing the contract, and add data protection terms."),

    ("survival_forever", "Term & Renewal", "Low", "Obligations that never expire",
     r"surviv\w+[^.]{0,60}(?:indefinitely|in perpetuity|without (?:limit|limitation) (?:in|as to) time)|"
     r"confidential\w*[^.]{0,60}(?:indefinitely|in perpetuity)",
     "An obligation that never ends is a long-term compliance burden.",
     "Set a fixed survival period, usually 2-5 years."),
]

COMPILED_RULES = [
    (rid, cat, sev, title, re.compile(pat, re.I), why, rec)
    for rid, cat, sev, title, pat, why, rec in RISK_RULES
]

# clause type that should exist -> (severity, why, recommendation)
EXPECTED_CLAUSES = {
    "Limitation of Liability": ("High",
        "Without a liability cap, exposure under the contract is unlimited by default.",
        "Add a mutual cap on liability and exclude indirect damages."),
    "Termination": ("High",
        "No stated way to end the contract or what happens on breach.",
        "Add termination for breach with a cure period, and termination rights on insolvency."),
    "Governing Law": ("Medium",
        "No governing law, so it is unclear whose law decides a dispute.",
        "State the governing law and the courts or seat of arbitration."),
    "Dispute Resolution": ("Medium",
        "No agreed process for disputes (negotiation, mediation, arbitration or courts).",
        "Add an escalation path and a forum for disputes."),
    "Confidentiality": ("Medium",
        "Information shared under the contract is not protected.",
        "Add mutual confidentiality obligations with a defined term."),
    "Payment": ("Medium",
        "Payment terms are not clearly stated.",
        "Specify amount, invoicing, due dates and late-payment terms."),
    "Indemnification": ("Low",
        "No indemnity. This may be fine, but third-party claims would fall under general law.",
        "Consider a limited, mutual indemnity for IP infringement and third-party claims."),
    "Force Majeure": ("Low",
        "No relief for events outside a party's control.",
        "Add a force majeure clause covering events, notice and a right to terminate if prolonged."),
    "Intellectual Property": ("Low",
        "Ownership of IP created or shared under the contract is not addressed.",
        "State who owns pre-existing and new IP, and what licences are granted."),
}

PERSONAL_DATA_RE = re.compile(r"personal (?:data|information)|customer data|user data", re.I)
MIN_SENTENCE_LEN = 20
MAX_EXCERPT = 400


def _excerpt(sentence):
    return sentence if len(sentence) <= MAX_EXCERPT else sentence[:MAX_EXCERPT].rsplit(" ", 1)[0] + "..."


def find_risky_wording(text):
    findings = []
    seen = set()

    for seg in segment_clauses(text):
        for sentence in split_sentences(seg["text"]):
            if len(sentence) < MIN_SENTENCE_LEN:
                continue

            for rid, cat, sev, title, rx, why, rec in COMPILED_RULES:
                if not rx.search(sentence):
                    continue

                key = (rid, sentence.lower())
                if key in seen:
                    continue
                seen.add(key)

                findings.append({
                    "kind": "Risky wording",
                    "id": rid,
                    "category": cat,
                    "severity": sev,
                    "title": title,
                    "why": why,
                    "recommendation": rec,
                    "excerpt": _excerpt(sentence),
                    "section": seg["heading"],
                })

    return findings


def find_missing_protections(text):
    present = {c["type"] for c in extract_clauses(text)}
    findings = []

    for ctype, (sev, why, rec) in EXPECTED_CLAUSES.items():
        if ctype in present:
            continue
        findings.append({
            "kind": "Missing protection",
            "id": "missing_" + re.sub(r"\W+", "_", ctype.lower()),
            "category": ctype,
            "severity": sev,
            "title": f"No {ctype} clause found",
            "why": why,
            "recommendation": rec,
            "excerpt": "",
            "section": "",
        })

    # data protection only matters if personal data is actually handled
    if "Data Protection" not in present and PERSONAL_DATA_RE.search(text):
        findings.append({
            "kind": "Missing protection",
            "id": "missing_data_protection",
            "category": "Data Protection",
            "severity": "High",
            "title": "Personal data mentioned but no data protection clause",
            "why": "The contract involves personal data but sets no rules for handling, security or breaches.",
            "recommendation": "Add data protection terms: purpose limits, security measures, breach notice and sub-processor rules.",
            "excerpt": "",
            "section": "",
        })

    return findings


def analyze_risks(text):
    """All findings, most severe first (document order within a severity)."""
    findings = find_risky_wording(text) + find_missing_protections(text)
    order = {id(f): i for i, f in enumerate(findings)}
    findings.sort(key=lambda f: (SEVERITY_ORDER[f["severity"]], order[id(f)]))
    return findings


def risk_score(findings):
    """
    0-100 score. Each distinct risk type counts once at full weight and repeats at a
    quarter weight, so a rule that fires 10 times does not drown out everything else.
    """
    total = 0.0
    counted = set()
    for f in findings:
        w = SEVERITY_WEIGHT[f["severity"]]
        if f["kind"] == "Missing protection":
            w *= 0.5      # absence is less certain than explicit bad wording
        if f["id"] in counted:
            w *= 0.25
        counted.add(f["id"])
        total += w
    return min(100, round(total))


def risk_level(score):
    if score >= 60:
        return "Critical"
    if score >= 35:
        return "High"
    if score >= 15:
        return "Moderate"
    return "Low"


def count_by_severity(findings):
    counts = {"High": 0, "Medium": 0, "Low": 0}
    for f in findings:
        counts[f["severity"]] += 1
    return counts
