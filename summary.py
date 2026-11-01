import re
from utils import clean_text
from clauses import (
    segment_clauses, extract_clauses, CLAUSE_TYPES,
    DURATION_RE, MONEY_RE, PERCENT_RE,
)
from obligations import split_sentences

MAX_CLAUSES = 12              # max bullets in a contract summary
MAX_SENTENCES_PER_CLAUSE = 2
MIN_CLAUSES_FOR_CONTRACT = 3  # fewer than this -> treat as a general document

MODAL_RE = re.compile(
    r"\b(?:shall|must|may|will|agrees? to|entitled to|liable|responsible|governed by|"
    r"terminate\w*|pay|payable|owns?|belongs?|retains?)\b", re.I)
NUMBER_RE = re.compile(r"\d")
SCOPE_HEADING_RE = re.compile(
    r"\b(?:services?|scope|deliverables?|purpose|work|supply|products?|engagement|"
    r"sale|purchase|lease|licen[sc]e grant|appointment)\b", re.I)


# ---------------------------------------------------------------------------
# Contract summary: parties + one key sentence per important clause
# ---------------------------------------------------------------------------

def _sentence_score(sentence):
    """Higher = more informative: amounts, durations, percentages, obligations."""
    words = len(sentence.split())
    if words < 5:
        return 0
    score = 0
    score += 2 * len(MONEY_RE.findall(sentence))
    score += 2 * len(DURATION_RE.findall(sentence))
    score += 2 * len(PERCENT_RE.findall(sentence))
    score += 1 if NUMBER_RE.search(sentence) else 0
    score += 1 if MODAL_RE.search(sentence) else 0
    if words > 45:                # very long sentences read badly in a summary
        score -= 1
    return score


def _best_sentences(clause_text):
    sentences = [s for s in split_sentences(clause_text) if len(s.split()) >= 5]
    if not sentences:
        return []

    # keep document order, but only the most informative ones
    scored = sorted(range(len(sentences)), key=lambda i: (-_sentence_score(sentences[i]), i))
    chosen = [i for i in scored[:MAX_SENTENCES_PER_CLAUSE]]
    # always include the first sentence (it normally states the core rule); extras must add info
    if 0 not in chosen:
        chosen = [0] + chosen[:MAX_SENTENCES_PER_CLAUSE - 1]
    chosen = sorted(set(chosen))

    result = [sentences[chosen[0]]]
    for i in chosen[1:]:
        if _sentence_score(sentences[i]) > 0:
            result.append(sentences[i])
    return result


def _overview(text):
    """Title and the opening sentence that normally names the parties and date."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    title = ""
    if lines and len(lines[0]) <= 80 and not lines[0].endswith("."):
        title = lines[0]

    segments = segment_clauses(text)
    preamble = ""
    if segments and not segments[0]["heading"]:
        sentences = split_sentences(segments[0]["text"])
        # the title line is part of the preamble text, so drop it
        sentences = [s for s in sentences if s.strip() != title]
        for s in sentences:
            if re.search(r"\b(?:between|by and between|made (?:on|as of)|entered into|among)\b", s, re.I):
                preamble = s
                break
        if not preamble and sentences:
            preamble = sentences[0]

    if title and preamble.startswith(title):
        preamble = preamble[len(title):].strip()
    return title, preamble


def _contract_summary(text, clauses):
    title, preamble = _overview(text)

    parts = []
    heading = f"**{title.title() if title.isupper() else title}**" if title else "**Contract summary**"
    parts.append(heading)
    if preamble:
        parts.append(preamble)

    importance_rank = {"High": 0, "Medium": 1, "Low": 2}
    # pick the most important clauses, then show them in document order
    ranked = sorted(enumerate(clauses), key=lambda ic: (importance_rank[ic[1]["importance"]], ic[0]))
    picked = sorted(ranked[:MAX_CLAUSES], key=lambda ic: ic[0])

    bullets = []

    # "what is this contract for" has no clause type, so find it from the section heading
    for seg in segment_clauses(text):
        if seg["heading"] and SCOPE_HEADING_RE.search(seg["heading"]):
            sentences = _best_sentences(seg["text"])
            if sentences:
                bullets.append("- **Scope:** " + " ".join(sentences))
            break

    for _, c in picked:
        sentences = _best_sentences(c["text"])
        if not sentences:
            continue
        label = c["type"]
        bullets.append(f"- **{label}:** " + " ".join(sentences))

    if bullets:
        parts.append("**Key points**")
        parts.append("\n".join(bullets))

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# General document summary: improved extractive
# ---------------------------------------------------------------------------

def _is_heading_line(line):
    line = line.strip()
    return len(line) <= 70 and not re.search(r"[.!?;,:]$", line) and len(line.split()) <= 9


def _prose_sentences(text, nlp):
    """Sentences from body text only: headings are removed so they never glue onto a sentence."""
    paragraphs, cur = [], []
    for line in text.split("\n"):
        if not line.strip() or _is_heading_line(line):
            if cur:
                paragraphs.append(" ".join(cur))
                cur = []
            continue
        cur.append(line.strip())
    if cur:
        paragraphs.append(" ".join(cur))

    sentences, para_of = [], []
    for pi, p in enumerate(paragraphs):
        for sent in nlp(p).sents:
            s = sent.text.strip()
            if 6 <= len(s.split()) <= 60:
                sentences.append(s)
                para_of.append(pi)
    return sentences, para_of


def _jaccard(a, b):
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if a and b else 0


def _extractive_summary(text, nlp, num_sentences):
    sentences, para_of = _prose_sentences(text, nlp)
    if not sentences:
        return text

    docs = [nlp(s) for s in sentences]

    freq = {}
    for d in docs:
        for t in d:
            if t.is_stop or t.is_punct or not t.is_alpha:
                continue
            w = t.lemma_.lower()
            freq[w] = freq.get(w, 0) + 1
    if not freq:
        return text

    top = max(freq.values())
    freq = {w: c / top for w, c in freq.items()}

    scores = []
    for i, d in enumerate(docs):
        words = [t.lemma_.lower() for t in d if t.is_alpha and not t.is_stop]
        if not words:
            scores.append(0.0)
            continue
        # average (not sum) so long sentences don't win just by being long
        s = sum(freq.get(w, 0) for w in words) / len(words)
        s += 0.15 * len(d.ents) / max(1, len(words) ** 0.5)
        if NUMBER_RE.search(sentences[i]):
            s += 0.05
        if i < 3:                  # opening sentences usually carry the topic
            s += 0.15 * (3 - i) / 3
        scores.append(s)

    def lemmas(i):
        return [t.lemma_.lower() for t in docs[i] if t.is_alpha and not t.is_stop]

    def is_duplicate(i, chosen):
        return any(_jaccard(lemmas(i), lemmas(j)) > 0.5 for j in chosen)

    by_score = sorted(range(len(sentences)), key=lambda i: -scores[i])
    chosen = []

    # First pass: the best sentence of each paragraph, so every topic is represented
    # (when there are more paragraphs than slots, the strongest paragraphs win).
    best_per_para = {}
    for i in by_score:
        best_per_para.setdefault(para_of[i], i)
    for i in sorted(best_per_para.values(), key=lambda i: -scores[i])[:num_sentences]:
        chosen.append(i)

    # Second pass: fill the remaining slots with the highest-scoring non-duplicates.
    for i in by_score:
        if len(chosen) >= num_sentences:
            break
        if i not in chosen and not is_duplicate(i, chosen):
            chosen.append(i)

    return " ".join(sentences[i] for i in sorted(chosen))


# ---------------------------------------------------------------------------

def summarize_text(text, nlp, num_sentences=None):
    text = clean_text(text)

    if len(text.split()) < 50:
        return text

    clauses = extract_clauses(text)
    if len(clauses) >= MIN_CLAUSES_FOR_CONTRACT:
        return _contract_summary(text, clauses)

    if num_sentences is None:
        num_sentences = max(3, min(8, round(len(text.split()) * 0.03)))

    return _extractive_summary(text, nlp, num_sentences)
