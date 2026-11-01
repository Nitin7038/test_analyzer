"""
obligations.py

Rule-based detection of contractual obligations, rights, prohibitions and
responsibilities.

Each sentence is checked for modal language ("shall", "may", "entitled to",
"shall not", "liable for", ...). For every hit we record:
    - type      Obligation / Right / Prohibition / Responsibility
    - party     who the statement applies to (best-effort, from the subject)
    - action    what the party must / may / must not do
    - condition leading "if ... / subject to ... / unless ..." qualifier
    - deadline  durations or timing words such as "within 30 days"
    - section   heading of the clause the sentence came from
"""

import re

from clauses import segment_clauses, DURATION_RE

# Order matters: the first matching rule wins, so the more specific
# (negative / right / liability) forms go before the generic "shall".
RULES = [
    ("Prohibition", re.compile(
        r"\b(?:shall not|neither party (?:shall|may|will|must)|must not|may not|will not|cannot|can not|agrees? not to|"
        r"is not permitted to|are not permitted to|is prohibited from|are prohibited from|"
        r"is not entitled to|undertakes? not to|shall in no event|"
        r"shall under no circumstances)\b", re.I)),
    ("Right", re.compile(
        r"\b(?:shall (?:be|have)|will (?:be|have)|is|are|has|have)\s+(?:the\s+)?"
        r"(?:entitled to|right to|option to|discretion to)|"
        r"\b(?:is|are) (?:permitted|authori[sz]ed|allowed) to|"
        r"\b(?:reserves?|retains?) the right|"
        r"\bhas the right|\bhave the right|\bentitled to|"
        r"\bmay\b", re.I)),
    ("Responsibility", re.compile(
        r"\b(?:shall be|will be|is|are|remains?|shall remain)\s+"
        r"(?:solely\s+|fully\s+|exclusively\s+)?(?:liable|responsible|accountable)\b|"
        r"\bbears? (?:all|the) (?:cost|costs|risk|risks|liability|expense|expenses)|"
        r"\bat (?:its|their|his|her) (?:own )?(?:cost|expense|risk)|"
        r"\bresponsibility (?:for|of)\b|\bliable for\b", re.I)),
    ("Obligation", re.compile(
        r"\b(?:shall|must|agrees? to|undertakes? to|is required to|are required to|"
        r"is obliged to|are obliged to|is obligated to|will be required to|"
        r"covenants? to|has to|have to|will)\b", re.I)),
]

CONDITION_RE = re.compile(
    r"^\s*((?:subject to|if|unless|provided that|in the event|upon|where|"
    r"in case|should|once|after|before|during|notwithstanding)\b[^,;]{3,160}),\s*", re.I)

TIMING_RE = re.compile(
    r"\b(?:immediately|promptly|forthwith|without delay|as soon as (?:reasonably )?practicable|"
    r"no later than [^,.;]{3,40}|on or before [^,.;]{3,40}|by (?:the )?(?:end of|[A-Z][a-z]+ \d{1,2})[^,.;]{0,30}|"
    r"within\s+(?:\w+\s+)?\(?\d+\)?\s*(?:business\s+|calendar\s+)?(?:days?|weeks?|months?|years?)|"
    r"(?:monthly|quarterly|annually|weekly|daily))\b", re.I)

COMPOUND_RE = re.compile(
    r"(?:,\s*)?\b(?:and|but|and also)\s+(?=(?:shall|must|may|will|agrees? to)\b)", re.I)

COLLECTIVE_RE =re.compile(
    r"\b(each|either|neither|both|any)\s+part(?:y|ies)\b", re.I)
NAMED_PARTY_RE = re.compile(
    r"((?:the\s+)?[A-Z][\w&.'\-]*(?:\s+(?:[A-Z][\w&.'\-]*|of|and|&))*)\s*$")

# words that look like a capitalised subject but are not a party
NOT_A_PARTY = {"This", "That", "The", "These", "Those", "Such", "Any", "All", "It", "If",
               "Section", "Article", "Clause", "Agreement", "Schedule", "Annexure", "Subject"}

MIN_SENTENCE_LEN = 25


def split_sentences(text):
    text = " ".join(text.split())
    return [s.strip() for s in re.split(r"(?<=[.;])\s+(?=[A-Z(\[\"'])", text) if s.strip()]


def _find_type(sentence):
    """Return (type, match) for the earliest-priority rule that matches."""
    for kind, rx in RULES:
        m = rx.search(sentence)
        if m:
            return kind, m
    return None, None


def _extract_party(prefix):
    """Best-effort subject of the sentence, taken from the text before the modal verb."""
    prefix = prefix.strip().rstrip(",")
    if not prefix:
        return "Unspecified"

    # a leading condition ("If X fails to pay, ...") belongs to the condition, not the subject
    if "," in prefix:
        prefix = prefix.rsplit(",", 1)[1].strip() or prefix

    m = COLLECTIVE_RE.search(prefix)
    if m and prefix[m.start():].count(" ") <= 3:
        return m.group(0).strip().capitalize()

    m = NAMED_PARTY_RE.search(prefix)
    if m:
        party = re.sub(r"^the\s+", "", m.group(1).strip(), flags=re.I)
        if party and party.split()[0] not in NOT_A_PARTY:
            return party

    words = prefix.split()
    if len(words) <= 5:
        return prefix
    return "Unspecified"


def _extract_condition(sentence):
    m = CONDITION_RE.match(sentence)
    if not m:
        return "", sentence
    return m.group(1).strip(), sentence[m.end():]


def _extract_deadline(text):
    for m in TIMING_RE.finditer(text):
        return m.group(0).strip()
    m = DURATION_RE.search(text)
    return m.group(0).strip() if m else ""


def extract_obligations(text):
    """
    Returns a list of dicts in document order:
        {type, party, action, sentence, condition, deadline, section}
    """
    results = []
    seen = set()

    for seg in segment_clauses(text):
        section = seg["heading"]
        for sentence in split_sentences(seg["text"]):
            if len(sentence) < MIN_SENTENCE_LEN:
                continue

            condition, core = _extract_condition(sentence)

            # "X must do A and shall not do B" -> two statements sharing subject X
            parts = COMPOUND_RE.split(core)
            party = None

            for part in parts:
                kind, m = _find_type(part)
                if not kind:
                    continue

                if party is None:
                    if m.group(0).lower().startswith("neither party"):
                        party = "Neither party"
                    else:
                        party = _extract_party(part[:m.start()])

                key = (sentence.lower(), part.lower())
                if key in seen:
                    continue
                seen.add(key)

                if kind == "Responsibility":
                    action = part[m.start():].strip(" ,;.")
                else:
                    action = part[m.end():].strip(" ,;.")

                results.append({
                    "type": kind,
                    "party": party,
                    "action": action or part,
                    "sentence": sentence,
                    "condition": condition,
                    "deadline": _extract_deadline(part),
                    "section": section,
                })

    return results


def group_by_party(items):
    """{party: [items]} with the most active parties first."""
    groups = {}
    for it in items:
        groups.setdefault(it["party"], []).append(it)
    return dict(sorted(groups.items(), key=lambda kv: (kv[0] == "Unspecified", -len(kv[1]), kv[0])))


def count_by_type(items):
    counts = {"Obligation": 0, "Right": 0, "Prohibition": 0, "Responsibility": 0}
    for it in items:
        counts[it["type"]] += 1
    return counts
