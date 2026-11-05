"""
financials.py

Rule-based extraction of financial terms from contracts.

Finds every monetary amount and every finance-related percentage, then works out:
    - category   Contract Value / Fee / Payment Schedule / Penalty / Interest / Tax /
                 Deposit / Liability Cap / Discount / Reimbursement / Other
    - frequency  One-time / Monthly / Quarterly / Annually / Per unit ...
    - timing     when it is due ("within 30 days", "upon delivery", ...)
    - payer      who pays, when the sentence says so
    - section    heading of the clause it came from

and a total contract value per currency: the value stated in the contract if there
is one, otherwise an estimate built from fees and payments (recurring fees are
multiplied by the contract term when the term can be found).
"""

import re

from clauses import segment_clauses
from obligations import split_sentences, TIMING_RE

# ---------------------------------------------------------------------------
# Amount parsing
# ---------------------------------------------------------------------------

CURRENCY_CODES = {
    "$": "USD", "us$": "USD", "usd": "USD", "dollar": "USD", "dollars": "USD",
    "₹": "INR", "inr": "INR", "rs": "INR", "rs.": "INR", "rupee": "INR", "rupees": "INR",
    "€": "EUR", "eur": "EUR", "euro": "EUR", "euros": "EUR",
    "£": "GBP", "gbp": "GBP", "pound": "GBP", "pounds": "GBP",
    "aud": "AUD", "cad": "CAD", "sgd": "SGD", "aed": "AED", "jpy": "JPY", "¥": "JPY",
}
CURRENCY_SYMBOL = {"USD": "$", "INR": "₹", "EUR": "€", "GBP": "£", "JPY": "¥"}

SCALE = {
    "thousand": 1e3, "k": 1e3,
    "lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5,
    "million": 1e6, "mn": 1e6, "m": 1e6,
    "crore": 1e7, "crores": 1e7, "cr": 1e7,
    "billion": 1e9, "bn": 1e9,
}

_NUM = r"\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_SCALE = r"(?:\s?(?:thousand|lakhs?|lacs?|million|mn|crores?|cr|billion|bn|k|m)\b)?"

# "$120,000", "Rs. 5,00,000", "USD 1.2 million", "₹ 10 lakhs"
MONEY_PREFIX_RE = re.compile(
    r"(?P<cur>US\$|USD|INR|EUR|GBP|AUD|CAD|SGD|AED|JPY|Rs\.?|₹|\$|€|£|¥)\s?"
    r"(?P<num>" + _NUM + r")(?P<scale>" + _SCALE + r")",
    re.I,
)
# "50,000 USD", "10 lakh rupees", "2,500 dollars"
MONEY_SUFFIX_RE = re.compile(
    r"\b(?P<num>" + _NUM + r")(?P<scale>" + _SCALE + r")\s?"
    r"(?P<cur>USD|INR|EUR|GBP|AUD|CAD|SGD|AED|JPY|dollars?|rupees?|euros?|pounds?)\b",
    re.I,
)
PERCENT_RE = re.compile(r"\b(?P<num>\d+(?:\.\d+)?)\s?(?:%|per\s?cent\b|percent\b)", re.I)

# a percentage only counts as a financial term when the sentence is about money
FINANCIAL_CONTEXT_RE = re.compile(
    r"\b(?:interest|penalt\w+|late|discount\w*|rebate|tax\w*|gst|vat|tds|advance|deposit|fee\w*|price\w*|"
    r"payment\w*|payable|pay|invoice\w*|retention|liquidated|damages|commission|royalt\w+|"
    r"escalat\w+|increase|markup|margin|consideration|cost\w*|charges?)\b",
    re.I,
)


def _parse_amount(num, scale):
    value = float(num.replace(",", ""))
    scale = (scale or "").strip().lower()
    return value * SCALE.get(scale, 1)


def _currency(code):
    return CURRENCY_CODES.get(code.strip().lower(), code.strip().upper())


def format_money(value, currency):
    symbol = CURRENCY_SYMBOL.get(currency)
    text = f"{value:,.2f}".rstrip("0").rstrip(".")
    return f"{symbol}{text}" if symbol else f"{currency} {text}"


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

# Earlier categories win ties: the specific ones (penalty, interest, ...) go first
# so "a penalty of $500 per day" is not filed as a generic fee.
CATEGORIES = [
    ("Penalty", [r"penalt\w+", r"liquidated damages", r"forfeit\w*", r"service credits?", r"\bfine\b"]),
    ("Interest", [r"interest", r"late (?:payment )?(?:fee|charge)s?", r"overdue", r"per annum", r"compounded"]),
    ("Tax", [r"\bgst\b", r"\bvat\b", r"\btds\b", r"tax\w*", r"withholding", r"\bduty\b", r"cess"]),
    ("Liability Cap", [r"liabilit\w+", r"shall not exceed", r"aggregate liability", r"\bcap(?:ped)?\b",
                       r"maximum (?:amount|liability)"]),
    ("Deposit / Security", [r"security deposit", r"deposit", r"bank guarantee", r"performance (?:bond|guarantee)",
                            r"retention", r"escrow", r"earnest money"]),
    ("Discount", [r"discount\w*", r"rebate", r"volume (?:discount|incentive)", r"waive[rd]?"]),
    ("Reimbursement", [r"reimburs\w+", r"out[- ]of[- ]pocket", r"expenses", r"travel"]),
    ("Payment Schedule", [r"instal(?:l)?ments?", r"milestones?", r"advance", r"upfront", r"up-front",
                          r"balance", r"upon (?:delivery|completion|acceptance|signing|execution)",
                          r"on (?:signing|execution)", r"tranche", r"progress payment", r"first payment"]),
    ("Fee", [r"fees?", r"charges?", r"subscription", r"retainer", r"licen[sc]e fee", r"royalt\w+",
             r"commission", r"rent", r"salary", r"remuneration", r"compensation", r"rate", r"per unit",
             r"per hour", r"hourly"]),
    ("Contract Value", [r"total (?:contract )?(?:value|price|consideration|amount|fees?|cost)",
                        r"contract (?:value|price|sum)", r"(?:aggregate|total) (?:value|consideration)",
                        r"purchase price", r"consideration", r"\bprice\b", r"lump sum"]),
]
COMPILED_CATEGORIES = [(name, [re.compile(r"\b" + p, re.I) for p in pats]) for name, pats in CATEGORIES]

# categories that make up what the contract is worth (others are contingent or caps)
VALUE_CATEGORIES = {"Contract Value", "Fee", "Payment Schedule"}

FREQUENCY_PATTERNS = [
    ("Monthly", r"\b(?:per|a|each|every)\s+(?:calendar\s+)?month\b|\bmonthly\b|/\s?month\b|\bp\.?m\.?\b"),
    ("Quarterly", r"\b(?:per|a|each|every)\s+quarter\b|\bquarterly\b"),
    ("Annually", r"\b(?:per|a|each|every)\s+(?:annum|year)\b|\bannual(?:ly)?\b|\byearly\b|\bp\.?a\.?\b|/\s?year\b"),
    ("Weekly", r"\b(?:per|a|each|every)\s+week\b|\bweekly\b"),
    ("Per day", r"\b(?:per|a|each|every)\s+(?:calendar\s+)?day\b|\bdaily\b"),
    ("Per hour", r"\b(?:per|an|each|every)\s+hour\b|\bhourly\b|/\s?h(?:ou)?r\b"),
    ("Per unit", r"\bper\s+(?:unit|device|item|piece|license|licence|user|seat|order)\b"),
    ("One-time", r"\bone[- ]time\b|\blump[- ]sum\b|\bupfront\b|\bup-front\b|\bnon-recurring\b|\bone-off\b"),
]
COMPILED_FREQUENCIES = [(name, re.compile(p, re.I)) for name, p in FREQUENCY_PATTERNS]

TIMING_EXTRA_RE = re.compile(
    r"\b(?:upon|on|at|prior to|before|after)\s+(?:the\s+)?(?:signing|execution|delivery|completion|acceptance|"
    r"receipt of (?:the |a )?(?:invoice|goods)|invoice|commencement|effective date|go-live|installation)\b|"
    r"\bin advance\b|\bin arrears\b",
    re.I,
)

PAYER_RE = re.compile(
    r"(?:the\s+)?(?P<party>[A-Z][\w&.'\-]*(?:\s+[A-Z][\w&.'\-]*){0,4})\s+"
    r"(?:shall|will|must|agrees? to|undertakes? to)\s+(?:\w+\s+){0,2}(?:pay|reimburse|deposit|remit)\b"
)
PAYABLE_BY_RE = re.compile(r"\b(?:payable|paid|borne)\s+by\s+(?:the\s+)?(?P<party>[A-Z][\w&.'\-]*(?:\s+[A-Z][\w&.'\-]*){0,3})")
NOT_A_PARTY = {"This", "The", "Such", "Each", "All", "Any", "It"}

WINDOW = 90   # characters either side of an amount used for classification
LEAD = 40     # characters just before an amount ("a fixed fee of $...") - the strongest signal


def _classify(sentence, start, end):
    window = sentence[max(0, start - WINDOW): min(len(sentence), end + WINDOW)]
    lead = sentence[max(0, start - LEAD): start]
    best, best_score = "Other", 0
    for name, patterns in COMPILED_CATEGORIES:
        score = 0
        for rx in patterns:
            score += 4 * len(rx.findall(lead))
            score += 2 * len(rx.findall(window))
            score += len(rx.findall(sentence))
        if score > best_score:          # strict ">" keeps the earlier (more specific) category on ties
            best, best_score = name, score
    return best


FREQUENCY_ONLY_RE = re.compile(r"^(?:monthly|quarterly|annually|weekly|daily)$", re.I)


def _frequency(sentence, start, end):
    """
    Only look right next to the amount: "$5,000 per month" or "monthly fee of $5,000".
    "payable in quarterly instalments" describes how a fee is split, not a recurring charge.
    """
    after = sentence[end: end + 30]
    before = sentence[max(0, start - 35): start]
    for zone in (after, before):
        for name, rx in COMPILED_FREQUENCIES:
            m = rx.search(zone)
            if not m or re.match(r"\s*(?:equal\s+)?instal", zone[m.end():], re.I):
                continue
            # "per day" belongs to the amount before it, so before an amount only
            # adjective forms count ("monthly fee of $X"), not "per X" / "/X"
            if zone is before and re.match(r"(?:per|a|an|each|every)\b|/", m.group(0), re.I):
                continue
            return name
    return ""


def _timing(sentence):
    m = TIMING_EXTRA_RE.search(sentence)
    if m:
        return m.group(0).strip()
    for m in TIMING_RE.finditer(sentence):
        if not FREQUENCY_ONLY_RE.match(m.group(0).strip()):   # frequency has its own column
            return m.group(0).strip()
    return ""


def _payer(sentence):
    for rx in (PAYER_RE, PAYABLE_BY_RE):
        m = rx.search(sentence)
        if m:
            party = re.sub(r"^The\s+", "", m.group("party").strip())
            if party and party.split()[0] not in NOT_A_PARTY:
                return party
    m = re.search(r"\b(each|either|both)\s+part(?:y|ies)\s+(?:shall|will)\s+(?:\w+\s+){0,2}pay", sentence, re.I)
    return m.group(1).capitalize() + " party" if m else ""


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def _money_matches(sentence):
    """All non-overlapping money matches in a sentence: (start, end, value, currency, text)."""
    found = []
    taken = []
    for rx in (MONEY_PREFIX_RE, MONEY_SUFFIX_RE):
        for m in rx.finditer(sentence):
            if any(m.start() < e and m.end() > s for s, e in taken):
                continue
            taken.append((m.start(), m.end()))
            found.append((m.start(), m.end(), _parse_amount(m.group("num"), m.group("scale")),
                          _currency(m.group("cur")), m.group(0).strip()))
    return sorted(found)


def extract_financial_terms(text):
    """
    Returns a list of dicts in document order:
        {category, kind ('amount'|'percent'), amount, value, currency, frequency,
         timing, payer, section, sentence}
    """
    terms = []
    seen = set()

    for seg in segment_clauses(text):
        section = seg["heading"]
        for sentence in split_sentences(seg["text"]):
            timing = _timing(sentence)
            payer = _payer(sentence)

            for start, end, value, currency, raw in _money_matches(sentence):
                key = (sentence, start)
                if key in seen or value == 0:
                    continue
                seen.add(key)
                terms.append({
                    "category": _classify(sentence, start, end),
                    "kind": "amount",
                    "amount": format_money(value, currency),
                    "value": value,
                    "currency": currency,
                    "frequency": _frequency(sentence, start, end),
                    "timing": timing,
                    "payer": payer,
                    "section": section,
                    "sentence": sentence,
                })

            if not FINANCIAL_CONTEXT_RE.search(sentence):
                continue
            for m in PERCENT_RE.finditer(sentence):
                key = (sentence, m.start())
                if key in seen:
                    continue
                seen.add(key)
                category = _classify(sentence, m.start(), m.end())
                terms.append({
                    "category": category,
                    "kind": "percent",
                    "amount": f"{float(m.group('num')):g}%",
                    "value": float(m.group("num")),
                    "currency": "%",
                    "frequency": _frequency(sentence, m.start(), m.end()),
                    "timing": timing,
                    "payer": payer,
                    "section": section,
                    "sentence": sentence,
                })

    return terms


# ---------------------------------------------------------------------------
# Total contract value
# ---------------------------------------------------------------------------

WORD_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                "eight": 8, "nine": 9, "ten": 10, "twelve": 12, "eighteen": 18, "twenty-four": 24,
                "thirty-six": 36}
TERM_RE = re.compile(
    r"\b(?:term|period|tenure|duration|continue[sd]?|remain in (?:full )?(?:force|effect)|valid|in force)\b"
    r"[^.;]{0,60}?\b(?:of|for|is|shall be|will be)\s+(?:a\s+(?:period|term)\s+of\s+)?"
    r"(?P<n>\d+|" + "|".join(WORD_NUMBERS) + r")\s*(?:\(\d+\)\s*)?(?P<unit>years?|months?)\b",
    re.I,
)
PERIODS_PER_MONTH = {"Monthly": 1, "Quarterly": 1 / 3, "Annually": 1 / 12, "Weekly": 52 / 12}


def find_term_months(text):
    """Contract term in months, if stated (e.g. 'continues for two years' -> 24)."""
    m = TERM_RE.search(" ".join(text.split()))
    if not m:
        return None
    n = m.group("n").lower()
    n = int(n) if n.isdigit() else WORD_NUMBERS[n]
    return n * 12 if m.group("unit").lower().startswith("year") else n


def total_contract_value(terms, text):
    """
    Per currency: {currency: {total, basis, components: [(label, value)], notes: [str]}}

    basis "Stated":    the contract states a total / contract price - the largest is used.
    basis "Estimated": one-time fees + recurring fees x term. Payment-schedule amounts are
                       treated as a breakdown of a fee when a one-time fee exists, so they
                       are not double counted.
    """
    term_months = find_term_months(text)
    result = {}

    currencies = sorted({t["currency"] for t in terms if t["kind"] == "amount"})
    for cur in currencies:
        items = [t for t in terms if t["kind"] == "amount" and t["currency"] == cur]
        notes = []

        stated = [t for t in items if t["category"] == "Contract Value" and t["frequency"] in ("", "One-time")]
        if stated:
            best = max(stated, key=lambda t: t["value"])
            result[cur] = {
                "total": best["value"],
                "basis": "Stated",
                "components": [(best["section"] or "Contract value", best["value"])],
                "notes": ["Taken from the contract value / price stated in the document."],
            }
            continue

        components = []
        seen_values = set()
        one_time_fees = [t for t in items if t["category"] == "Fee" and t["frequency"] in ("", "One-time")]

        for t in items:
            if t["category"] not in VALUE_CATEGORIES:
                continue
            if t["category"] == "Payment Schedule" and one_time_fees:
                continue   # instalments / advances are usually a split of the fee
            freq = t["frequency"]
            label = f"{t['category']}" + (f" - {t['section']}" if t["section"] else "")

            if freq in PERIODS_PER_MONTH:
                if not term_months:
                    notes.append(f"{format_money(t['value'], cur)} {freq.lower()} not included: contract term not found.")
                    continue
                periods = term_months * PERIODS_PER_MONTH[freq]
                key = (t["value"], freq)
                if key in seen_values:
                    continue
                seen_values.add(key)
                components.append((f"{label} ({format_money(t['value'], cur)} {freq.lower()} x {periods:g})",
                                   t["value"] * periods))
            elif freq in ("Per unit", "Per hour", "Per day"):
                notes.append(f"{format_money(t['value'], cur)} {freq.lower()} not included: depends on usage.")
            else:
                key = (t["value"], "once")
                if key in seen_values:
                    continue
                seen_values.add(key)
                components.append((label, t["value"]))

        if not components:
            continue

        if term_months:
            notes.insert(0, f"Contract term found: {term_months} months.")
        if any(t["category"] == "Payment Schedule" for t in items) and one_time_fees:
            notes.append("Instalment / advance amounts are treated as part of the fee, not added again.")
        notes.append("Excludes taxes, penalties, interest, deposits and liability caps.")

        result[cur] = {
            "total": sum(v for _, v in components),
            "basis": "Estimated",
            "components": components,
            "notes": notes,
        }

    return result


def count_by_category(terms):
    counts = {}
    for t in terms:
        counts[t["category"]] = counts.get(t["category"], 0) + 1
    order = [name for name, _ in CATEGORIES] + ["Other"]
    return dict(sorted(counts.items(), key=lambda kv: order.index(kv[0])))
