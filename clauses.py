"""
clauses.py

Rule-based legal clause extraction and classification.

1. Split the contract into clause segments (numbered / ARTICLE / SECTION headings,
   falling back to sentence grouping when the document has no headings).
2. Classify each segment into a clause type by weighted keyword patterns
   (heading matches count more than body matches).
3. Pull out key terms (durations, amounts, percentages) for quick scanning.
"""

import re

# importance shown to the user: High / Medium / Low
CLAUSE_TYPES = {
    "Termination": {
        "importance": "High",
        "patterns": [r"terminat\w*", r"notice of (?:termination|non-renewal)", r"for cause",
                     r"for convenience", r"breach", r"cure period", r"expir\w+"],
    },
    "Payment": {
        "importance": "High",
        "patterns": [r"payment\w*", r"invoice\w*", r"fees?", r"price\w*", r"compensation",
                     r"late (?:fee|interest)", r"remuneration", r"consideration", r"taxes"],
    },
    "Indemnification": {
        "importance": "High",
        "patterns": [r"indemnif\w+", r"indemnit\w+", r"hold harmless", r"defend", r"third[- ]party claims?"],
    },
    "Limitation of Liability": {
        "importance": "High",
        "patterns": [r"limitation of liability", r"liabilit\w+", r"consequential damages",
                     r"indirect damages", r"aggregate liability", r"shall not be liable",
                     r"in no event", r"liability cap"],
    },
    "Confidentiality": {
        "importance": "High",
        "patterns": [r"confidential\w*", r"non-disclosure", r"\bnda\b", r"proprietary information",
                     r"trade secrets?", r"disclos\w+"],
    },
    "Intellectual Property": {
        "importance": "High",
        "patterns": [r"intellectual property", r"\bip\b", r"copyright\w*", r"patents?", r"trademarks?",
                     r"licen[sc]e\w*", r"work product", r"work made for hire", r"ownership"],
    },
    "Governing Law": {
        "importance": "Medium",
        "patterns": [r"governing law", r"governed by", r"laws of", r"jurisdiction", r"venue",
                     r"construed in accordance"],
    },
    "Dispute Resolution": {
        "importance": "Medium",
        "patterns": [r"dispute\w*", r"arbitrat\w+", r"mediation", r"litigation",
                     r"courts? of", r"resolution of disputes", r"injunctive relief"],
    },
    "Term & Renewal": {
        "importance": "Medium",
        "patterns": [r"initial term", r"renewal", r"renew\w*", r"effective date",
                     r"term of (?:this|the) agreement", r"auto(?:matic(?:ally)?)?[- ]renew\w*",
                     r"\bterm\b"],
    },
    "Warranties & Representations": {
        "importance": "Medium",
        "patterns": [r"warrant\w+", r"represent\w*", r"as is", r"disclaimer", r"merchantability",
                     r"fitness for a particular purpose"],
    },
    "Non-Compete / Non-Solicit": {
        "importance": "High",
        "patterns": [r"non-?compet\w+", r"non-?solicit\w*", r"restrictive covenant",
                     r"(?<!non-)exclusivity", r"shall not (?:compete|solicit)"],
    },
    "Force Majeure": {
        "importance": "Medium",
        "patterns": [r"force majeure", r"act of god", r"acts of god", r"beyond (?:its|their) reasonable control",
                     r"natural disaster", r"war", r"pandemic"],
    },
    "Data Protection": {
        "importance": "Medium",
        "patterns": [r"personal data", r"data protection", r"privacy", r"gdpr", r"data breach",
                     r"data processing", r"security measures"],
    },
    "Insurance": {
        "importance": "Low",
        "patterns": [r"insurance", r"insured", r"coverage", r"policy limits?"],
    },
    "Assignment": {
        "importance": "Low",
        "patterns": [r"assign\w*", r"novation", r"subcontract\w*", r"change of control"],
    },
    "Notices": {
        "importance": "Low",
        "patterns": [r"notices?", r"in writing", r"registered mail", r"courier", r"deemed (?:received|delivered)"],
    },
    "Amendment & Waiver": {
        "importance": "Low",
        "patterns": [r"amend\w*", r"modif\w+", r"waiver", r"waive\w*"],
    },
    "Entire Agreement": {
        "importance": "Low",
        "patterns": [r"entire agreement", r"supersede\w*", r"prior (?:agreements|understandings)"],
    },
    "Severability": {
        "importance": "Low",
        "patterns": [r"severab\w+", r"invalid or unenforceable", r"remainder of this agreement"],
    },
}

# Headings are strongly indicative, so they carry a larger weight than body text.
HEADING_WEIGHT = 6
BODY_WEIGHT = 1
BODY_CAP = 6          # max body score contributed by a single pattern
MIN_SCORE = 3

HEADING_RE = re.compile(
    r"^\s*(?:"
    r"(?:ARTICLE|SECTION|CLAUSE|PART|SCHEDULE|ANNEXURE|APPENDIX|EXHIBIT)\s+[A-Z0-9IVXLC]+\b[.:\-)]?"
    r"|\d+(?:\.\d+)+[.)]?"           # "12.1" / "12.1."
    r"|\d+[.)]"                     # "12." / "12)"
    r")\s*(?P<rest>.*)$",
    re.I,
)

DURATION_RE = re.compile(r"\b(?:\w+\s+)?\(?\d+\)?\s*(?:business\s+|calendar\s+)?(?:days?|weeks?|months?|years?)\b", re.I)
MONEY_RE = re.compile(r"(?:USD|INR|EUR|GBP|Rs\.?|₹|\$|€|£)\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:million|billion|lakhs?|crores?))?", re.I)
PERCENT_RE = re.compile(r"\b\d+(?:\.\d+)?\s?%")


def _split_heading(rest):
    """Return (heading, body) from the text that follows a section number."""
    rest = rest.strip()
    m = re.match(r"^(?P<h>[^.:–—]{2,70}?)\s*(?:[.:–—]|\s-\s)\s*(?P<b>.+)$", rest)
    if m and len(m.group("h").split()) <= 8:
        return m.group("h").strip(), m.group("b").strip()
    if len(rest) <= 70 and not rest.endswith("."):
        return rest, ""
    return "", rest


def segment_clauses(text):
    """Split text into [{'heading', 'text'}] by top-level headings."""
    lines = [l.strip() for l in text.replace("\r", "").split("\n") if l.strip()]

    segments = []
    cur = None
    preamble = []

    for line in lines:
        m = HEADING_RE.match(line)
        if m:
            heading, body = _split_heading(m.group("rest"))
            # a bare number line like "3." gives no heading; keep it attached to the next line
            cur = {"heading": heading, "number": line.split()[0], "lines": [body] if body else []}
            segments.append(cur)
        elif cur is not None:
            # an all-caps / short line right after an empty heading becomes its heading
            if not cur["heading"] and not cur["lines"] and len(line) <= 70 and not line.endswith("."):
                cur["heading"] = line
            else:
                cur["lines"].append(line)
        else:
            preamble.append(line)

    result = []
    if preamble:
        result.append({"heading": "", "text": " ".join(preamble)})
    for s in segments:
        body = " ".join(s["lines"]).strip()
        if s["heading"] or body:
            result.append({"heading": s["heading"], "text": body})

    # Documents without headings: fall back to grouping sentences.
    if len([s for s in result if s["heading"]]) < 3:
        return _segment_by_sentences(text)

    return result


def _segment_by_sentences(text):
    sentences = re.split(r"(?<=[.;])\s+(?=[A-Z(])", " ".join(text.split()))
    return [{"heading": "", "text": s.strip()} for s in sentences if len(s.strip()) > 40]


def _score(heading, body):
    scores = {}
    heading = heading or ""
    for name, spec in CLAUSE_TYPES.items():
        score = 0
        for pat in spec["patterns"]:
            rx = re.compile(r"\b" + pat, re.I)
            if heading and rx.search(heading):
                score += HEADING_WEIGHT
            hits = len(rx.findall(body))
            score += min(hits * BODY_WEIGHT, BODY_CAP)
        if score:
            scores[name] = score
    return scores


def _key_terms(text):
    terms = []
    for rx in (DURATION_RE, MONEY_RE, PERCENT_RE):
        for m in rx.finditer(text):
            t = m.group(0).strip()
            if t not in terms:
                terms.append(t)
    return terms[:6]


def extract_clauses(text, include_other=False):
    """
    Returns a list of clause dicts in document order:
        {type, importance, heading, text, confidence, key_terms, also}
    """
    clauses = []

    for seg in segment_clauses(text):
        body = seg["text"]
        scores = _score(seg["heading"], body)
        if not scores:
            continue

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        best, best_score = ranked[0]

        # headingless segments (sentences) have less evidence, so a lower bar
        if best_score < (MIN_SCORE if seg["heading"] else MIN_SCORE - 1):
            continue

        total = sum(scores.values())
        clauses.append({
            "type": best,
            "importance": CLAUSE_TYPES[best]["importance"],
            "heading": seg["heading"],
            "text": body,
            "confidence": round(best_score / total, 2),
            "key_terms": _key_terms(body),
            "also": [n for n, s in ranked[1:3] if s >= MIN_SCORE * 2],
        })

    return clauses


def summarize_clauses(clauses):
    """Counts per clause type, ordered High -> Low importance."""
    order = {"High": 0, "Medium": 1, "Low": 2}
    counts = {}
    for c in clauses:
        counts[c["type"]] = counts.get(c["type"], 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (order[CLAUSE_TYPES[kv[0]]["importance"]], kv[0])))
