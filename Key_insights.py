import re

# Loaded on first use rather than at import time, so it doesn't slow app startup.
_nlp = None


def _get_nlp():
    global _nlp
    if _nlp is None:
        import spacy
        _nlp = spacy.load("en_core_web_sm")
    return _nlp

IMPORTANT_KEYWORDS = [

    # Business
    "revenue", "profit", "growth", "investment",
    "budget", "expansion", "target", "launch",

    # Research
    "objective", "methodology", "results",
    "findings", "conclusion", "future work",

    # Resume
    "experience", "skills", "education",
    "certification", "project",

    # Meeting Notes
    "action item", "deadline", "decision",
    "assigned", "responsible",

    # Legal / Contract
    "agreement", "payment", "obligation",
    "liability", "termination", "penalty"
]


def extract_key_insights(text):

    nlp = _get_nlp()
    doc = nlp(text)

    scored_sentences = []

    for sent in doc.sents:

        sentence = sent.text.strip()

        if len(sentence) < 20:
            continue

        score = 0

        # Numbers
        if re.search(r"\d+", sentence):
            score += 2

        # Money
        if "$" in sentence or "₹" in sentence:
            score += 3

        # Percentages
        if "%" in sentence:
            score += 3

        # Dates
        if re.search(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", sentence):
            score += 2

        # Named entities
        score += len(nlp(sentence).ents)

        # Important keywords
        for keyword in IMPORTANT_KEYWORDS:
            if keyword.lower() in sentence.lower():
                score += 2

        if score > 2:
            scored_sentences.append((sentence, score))

    scored_sentences.sort(
        key=lambda x: x[1], 
        reverse=True
    )

    insights = []

    for sentence, score in scored_sentences[:7]:
        if sentence not in insights:
            insights.append(sentence)

    return insights