"""
explainer.py

Plain-English explainer: rewrites contract clauses so non-lawyers can follow them.

Runs locally with deterministic rules, no LLM:
    1. Tidy up: "(hereinafter referred to as the "Seller", which expression ...)"
       becomes (the "Seller"), and "thirty (30)" becomes "30".
    2. Replace legalese with everyday words ("pursuant to" -> "under").
    3. Split long sentences at semicolons and "provided that".
    4. Add a one-line "what this means" for the clause type.

Safety: a rewritten sentence must keep every number and every negation of the
original. If it doesn't, the original sentence is kept, because a simpler sentence
with a changed meaning is worse than a hard one.
"""

import re

from clauses import segment_clauses, extract_clauses
from obligations import split_sentences

# What each clause type is for, in everyday language.
CLAUSE_MEANING = {
    "Termination": "How and when this contract can end, and what happens if someone breaks it.",
    "Payment": "How much is paid, when it is due, and what happens if payment is late.",
    "Indemnification": "Who pays if someone else makes a claim or a loss occurs because of this contract.",
    "Limitation of Liability": "The most a party can be made to pay if something goes wrong.",
    "Confidentiality": "What information must be kept secret, and for how long.",
    "Intellectual Property": "Who owns the work, ideas, brands and designs involved.",
    "Governing Law": "Which country's or state's law applies to this contract.",
    "Dispute Resolution": "How disagreements are settled, for example by arbitration or in court.",
    "Term & Renewal": "When this contract starts, how long it lasts, and whether it renews.",
    "Warranties & Representations": "The promises each party makes about facts or about quality.",
    "Non-Compete / Non-Solicit": "Limits on working with competitors, or on hiring or approaching certain people.",
    "Force Majeure": "What happens if an event outside anyone's control stops a party from performing.",
    "Data Protection": "How personal information must be handled and kept safe.",
    "Insurance": "What insurance a party must hold.",
    "Assignment": "Whether a party can pass this contract to someone else.",
    "Notices": "How official messages must be sent between the parties.",
    "Amendment & Waiver": "How this contract can be changed, and what happens if a right is not used.",
    "Entire Agreement": "This document replaces earlier discussions and agreements on the same subject.",
    "Severability": "If one part is found invalid, the rest of the contract still applies.",
    "Parties & Introduction": "Who is signing this contract and when it takes effect.",
    "General": "A general term of this contract.",
}

# Terms that have no simple one-word swap, so they are explained alongside the clause.
GLOSSARY = {
    "material breach": "A serious failure to do what the contract requires, not a minor slip.",
    "breach": "Failing to do what the contract requires.",
    "liable": "Legally responsible, and possibly required to pay.",
    "indemnity": "A promise to cover someone else's losses.",
    "consequential damages": "Indirect losses caused by a problem, such as lost profits.",
    "indirect damages": "Losses that do not follow directly from the problem, such as lost business.",
    "liquidated damages": "A fixed amount agreed in advance, paid if a party breaks a promise.",
    "arbitration": "Settling a dispute before a private decision-maker instead of a court.",
    "jurisdiction": "Which courts have the power to decide a dispute.",
    "force majeure": "Major events outside anyone's control, such as natural disasters or war.",
    "intellectual property": "Legal ownership of ideas and creations, such as software, brands and designs.",
    "third party": "Someone who is not one of the parties to this contract.",
    "third parties": "People or companies who are not parties to this contract.",
    "successors": "Whoever takes over a company, for example after a merger.",
    "permitted assigns": "Others the contract allows to take over a party's rights.",
    "warranty": "A promise that something is true or will work as described.",
    "non-exclusive": "Either party is free to do the same business with others.",
    "lien": "A legal claim on property until a debt is paid.",
    "escrow": "Money or documents held by a neutral third party until conditions are met.",
    "waiver": "Choosing to give up a right.",
}

NUMBER_WORDS = (
    "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|"
    "twenty[- ]four|thirty|forty[- ]five|forty|fifty|sixty|seventy|ninety|hundred|"
    "one hundred(?: and)? twenty|one hundred(?: and)? eighty|three hundred(?: and)? sixty[- ]five"
)

# Order matters: longer phrases first, so they are not broken up by shorter rules.
REWRITES = [
    # defined terms and fillers
    (r"\(\s*hereinafter\s+(?:referred to as|called)\s+(?:the\s+)?[\"“']?([\w ]+?)[\"”']?\s*(?:,[^)]*)?\)", r'(the "\1")'),
    (r"\b(?:" + NUMBER_WORDS + r")\s*\((\d+)\)", r"\1"),
    (r"\bfor the avoidance of doubt\b", "to be clear"),
    (r"\bincluding,? (?:but not limited to|without limitation)\b,?", "including"),
    (r"\bsubject to the terms (?:and conditions )?of this agreement,?\s*", "under this Agreement, "),
    (r"\bin witness whereof\b", "to confirm this"),
    (r"\bby and between\b", "between"),
    (r"\bany and all\b", "all"),

    # modal phrases, before the general "shall" rules
    (r"\bin no event shall (.{3,80}?) be liable\b", r"\1 will never be liable"),
    (r"\bunder no circumstances shall (.{3,80}?) be liable\b", r"\1 will never be liable"),
    (r"\bshall be entitled to\b", "can"),
    (r"\b(?:shall|will) have the right to\b", "can"),
    (r"\bis entitled to\b", "can"),
    (r"\bare entitled to\b", "can"),
    (r"\bshall be governed by\b", "is governed by"),
    (r"\bshall be deemed to be\b", "will be treated as"),
    (r"\bshall be deemed\b", "will be treated as"),
    (r"\bdeemed to be\b", "treated as"),
    (r"\b(Agreement|Contract|Term) shall\b", r"\1 will"),
    # "shall" states a fact here, not a duty, so "must" would change the meaning
    (r"\b(no|neither|nor)\b([^.;]{0,50}?)\bshall\b", r"\1\2will"),
    (r"\bshall( not)? (be|continue|remain|apply|survive|prevail|bear|expire|become|have|include|mean|take effect)\b",
     r"will\1 \2"),
    (r"\bshall not\b", "must not"),
    (r"\bshall\b", "must"),

    # conditions and connectors
    (r"\bin the event that\b", "if"),
    (r"\bin the event of\b", "if there is"),
    (r"\bin case of\b", "if there is"),
    (r"\bnotwithstanding\b", "despite"),
    (r"\bpursuant to\b", "under"),
    (r"\bin accordance with\b", "following"),
    (r"\bin compliance with\b", "following"),
    (r"\bwith respect to\b", "for"),
    (r"\bin respect of\b", "for"),
    (r"\bin relation to\b", "about"),
    (r"\bby virtue of\b", "because of"),
    (r"\bon behalf of\b", "for"),
    (r"\bprior to\b", "before"),
    (r"\bsubsequent to\b", "after"),
    (r"\bin order to\b", "to"),
    (r"\bfor the purposes? of\b", "for"),

    # "here-" and "there-" words
    (r"\bhereby\s+", ""),
    (r"\bhereinafter\b", "from now on"),
    (r"\bherein\b", "in this Agreement"),
    (r"\bhereof\b", "of this Agreement"),
    (r"\bhereto\b", "to this Agreement"),
    (r"\bhereunder\b", "under this Agreement"),
    (r"\bthereof\b", "of it"),
    (r"\btherein\b", "in it"),
    (r"\bthereto\b", "to it"),
    (r"\bthereafter\b", "after that"),
    (r"\bthe (?:aforesaid|aforementioned|said)\b", "that"),
    (r"\bforthwith\b", "immediately"),

    # legal terms of art
    (r"\bindemnify and hold harmless\b", "protect and compensate"),
    (r"\bindemnify,? defend,? and hold harmless\b", "protect, defend and compensate"),
    (r"\bindemnif(?:y|ies)\b", "compensate"),
    (r"\bat (?:its|their) (?:sole|absolute|sole and absolute) discretion\b", "entirely as it chooses"),
    (r"\bin (?:its|their) (?:sole|absolute|sole and absolute) discretion\b", "entirely as it chooses"),
    (r"\bnull and void\b", "invalid"),
    (r"\bin full force and effect\b", "in effect"),
    (r"\bforce and effect\b", "effect"),
    (r"\bmutatis mutandis\b", "with the necessary changes"),
    (r"\binter alia\b", "among other things"),
    (r"\bbona fide\b", "genuine"),
    (r"\bjointly and severally\b", "together and individually"),
    (r"\bexecution of this agreement\b", "signing of this Agreement"),

    # everyday words
    (r"\bcure\b", "fix"),
    (r"\bcured\b", "fixed"),
    (r"\bterminate\b", "end"),
    (r"\bterminates\b", "ends"),
    (r"\bterminated\b", "ended"),
    (r"\bcommencement\b", "start"),
    (r"\bcommence\b", "start"),
    (r"\bcommences\b", "starts"),
    (r"\butili[sz]e\b", "use"),
    (r"\bfurnish\b", "provide"),
    (r"\brender\b", "provide"),
    (r"\bremit\b", "pay"),
    (r"\bobtain\b", "get"),
    (r"\bassist\b", "help"),
    (r"\bensure\b", "make sure"),
    (r"\bsufficient\b", "enough"),
    (r"\badditional\b", "extra"),
    (r"\bapproximately\b", "about"),
    (r"\bsolely\b", "only"),
    (r"\bfails? to\b", lambda m: "does not" if m.group(0).lower() == "fails to" else "do not"),
]
COMPILED_REWRITES = [(re.compile(p, re.I), r) for p, r in REWRITES]

SUBCLAUSE_RE = re.compile(r"(?:^|(?<=[.;:]\s))(\d+\.\d+)\.?\s+(?=[A-Z(])")
NUMBER_RE = re.compile(r"\d[\d,.]*\d|\d")
NEGATION_RE = re.compile(r"\b(?:not|never|no|neither|nor|without|unless|except)\b", re.I)
# wording the rules remove on purpose; negative words inside it don't change the meaning
BOILERPLATE_RE = re.compile(
    r"\(\s*hereinafter[^)]*\)|\b(?:but not limited to|without limitation)\b", re.I)
FAILS_TO_RE = re.compile(r"\bfails? to\b", re.I)


def _match_case(replacement, original):
    """Keep a capital letter at the start of a replaced phrase."""
    if original[:1].isupper() and replacement[:1].islower():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def _apply_rules(sentence):
    for rx, repl in COMPILED_REWRITES:
        if callable(repl):
            sentence = rx.sub(lambda m: _match_case(repl(m), m.group(0)), sentence)
        elif "\\" in repl:                   # back-references: leave casing to the group
            sentence = rx.sub(repl, sentence)
        else:
            sentence = rx.sub(lambda m, r=repl: _match_case(r, m.group(0)), sentence)

    sentence = re.sub(r"\s+([,.;:])", r"\1", sentence)
    sentence = re.sub(r"\s{2,}", " ", sentence).strip()
    return sentence


def _is_safe(original, rewritten):
    """The rewrite must keep every number and every negation."""
    if sorted(NUMBER_RE.findall(original)) != sorted(NUMBER_RE.findall(rewritten)):
        return False
    # "does not" replaces "fails to", which is the one rule that adds a negative word
    expected = len(NEGATION_RE.findall(BOILERPLATE_RE.sub("", original))) + len(FAILS_TO_RE.findall(original))
    return len(NEGATION_RE.findall(rewritten)) == expected


def _split_long(sentence):
    """Break a sentence at "provided that" and at semicolons, but never at "; or"."""
    sentence = re.sub(r"[;,]\s*provided(?:,)? (?:however,? )?that\s+", ". However, ", sentence, flags=re.I)
    parts = re.split(r";\s+(?:and\s+)?(?!or\b)|(?<=\.)\s+(?=However, )", sentence)
    return [p.strip() for p in parts if p and p.strip()]


def _finish(sentence):
    sentence = sentence.strip(" ;,")
    if not sentence:
        return ""
    sentence = sentence[0].upper() + sentence[1:]
    return sentence if sentence[-1] in '.!?:"”)' else sentence + "."


def simplify_sentence(sentence):
    """Plain-English version of one sentence, as a list of short sentences."""
    rewritten = _apply_rules(sentence)
    if not _is_safe(sentence, rewritten):
        rewritten = sentence
    return [s for s in (_finish(p) for p in _split_long(rewritten)) if s]


def simplify_text(text):
    """Plain-English version of a clause body, as a list of points."""
    # sub-clauses ("7.1 ...") become separate points, and keep their number
    matches = list(SUBCLAUSE_RE.finditer(text))
    if matches:
        chunks = []
        if text[:matches[0].start()].strip():
            chunks.append(("", text[:matches[0].start()]))
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            chunks.append((m.group(1), text[m.end():end]))
    else:
        chunks = [("", text)]

    points = []
    for number, chunk in chunks:
        simple = []
        for sentence in split_sentences(chunk):
            simple.extend(simplify_sentence(sentence))
        if simple:
            points.append((f"{number} " if number else "") + " ".join(simple))
    return points


# ---------------------------------------------------------------------------
# Readability (Flesch Reading Ease: higher is easier, 60+ is plain English)
# ---------------------------------------------------------------------------

def explain_terms(text):
    """Glossary entries for legal terms in the text; longer terms hide the shorter ones inside them."""
    found = []
    for term in sorted(GLOSSARY, key=len, reverse=True):
        if re.search(r"\b" + re.escape(term) + r"\b", text, re.I) and not any(term in f for f in found):
            found.append(term)
    return [(t, GLOSSARY[t]) for t in sorted(found)]


def _syllables(word):
    word = re.sub(r"[^a-z]", "", word.lower())
    if not word:
        return 0
    count = len(re.findall(r"[aeiouy]+", word))
    if word.endswith("e") and not word.endswith("le") and count > 1:
        count -= 1
    return max(1, count)


def readability(text):
    words = re.findall(r"[A-Za-z][A-Za-z'\-]*", text)
    if not words:
        return 0.0
    sentences = max(1, len(re.findall(r"[.!?;]+(?:\s|$)", text)))
    syllables = sum(_syllables(w) for w in words)
    score = 206.835 - 1.015 * (len(words) / sentences) - 84.6 * (syllables / len(words))
    return round(max(0.0, min(100.0, score)), 1)


def reading_level(score):
    if score >= 60:
        return "Easy"
    if score >= 50:
        return "Fairly hard"
    if score >= 30:
        return "Hard"
    return "Very hard"


# ---------------------------------------------------------------------------

def explain_clauses(text):
    """
    Every clause in document order:
        {type, importance, heading, original, points, meaning, score_before, score_after}
    Sections the classifier can't place are kept as "General", so nothing is skipped.
    """
    classified = {(c["heading"], c["text"]): c for c in extract_clauses(text)}
    results = []

    for i, seg in enumerate(segment_clauses(text)):
        clause = classified.get((seg["heading"], seg["text"]))

        if clause:
            ctype, importance = clause["type"], clause["importance"]
        elif i == 0 and not seg["heading"]:
            ctype, importance = "Parties & Introduction", "Low"
        elif seg["heading"]:
            ctype, importance = "General", "Low"
        else:
            continue                         # stray unclassified sentence in a headingless document

        # the title line ends up in the preamble: "MASTER SALES AGREEMENT THIS MASTER ..."
        body = re.sub(r"^[A-Z][A-Z'&\- ]{3,80}\s+(?=THIS\b|This\b)", "", seg["text"]) if i == 0 else seg["text"]

        points = simplify_text(body)
        if not points:
            continue

        results.append({
            "type": ctype,
            "importance": importance,
            "heading": seg["heading"],
            "original": seg["text"],
            "points": points,
            "meaning": CLAUSE_MEANING[ctype],
            "terms": explain_terms(seg["text"]),
            "score_before": readability(seg["text"]),
            "score_after": readability(" ".join(points)),
        })

    return results


def average_scores(explained):
    """(before, after) averages, weighted by clause length so long clauses count more."""
    weight = sum(len(c["original"]) for c in explained) or 1
    before = sum(c["score_before"] * len(c["original"]) for c in explained) / weight
    after = sum(c["score_after"] * len(c["original"]) for c in explained) / weight
    return round(before, 1), round(after, 1)
