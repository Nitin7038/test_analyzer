"""
entities.py (starter skeleton)

Production-oriented legal entity extractor.
This is a scaffold intended to be expanded.
"""

import re
from collections import defaultdict

COMPANY_SUFFIXES = (
    "PRIVATE LIMITED","LIMITED","LLP","LTD","INC","CORPORATION","COMPANY","PLC"
)

ROLE_PATTERNS = {
    "Seller": r'referred to as\s+the\s+"?Seller"?',
    "Buyer": r'referred to as\s+the\s+"?Buyer"?',
    "Licensor": r'referred to as\s+the\s+"?Licensor"?',
    "Licensee": r'referred to as\s+the\s+"?Licensee"?',
}

DATE_RE = re.compile(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}",re.I)

def unique(seq):
    out=[]
    seen=set()
    for s in seq:
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    return out

def extract_companies(text, doc):
    companies=[]
    for ent in doc.ents:
        if ent.label_=="ORG":
            t=ent.text.strip()
            if any(x in t.upper() for x in COMPANY_SUFFIXES):
                companies.append(t)

    # fallback: uppercase company names
    pat=r'([A-Z][A-Z0-9&.,() \-]+(?:PRIVATE LIMITED|LIMITED|LLP|LLC|LTD|INC|CORPORATION|COMPANY))'
    companies.extend(re.findall(pat,text))
    return unique(companies)

def extract_parties(text, companies):
    parties=[]
    for c in companies:
        role=None
        for r,p in ROLE_PATTERNS.items():
            m=re.search(re.escape(c)+r'.{0,250}?'+p,text,re.I|re.S)
            if m:
                role=r
                break
        parties.append(f"{c} ({role})" if role else c)
    return unique(parties)

def extract_people(text, doc):
    """
    Extract people involved in the contract.

    Priority:
    1. Signature block names (highest confidence)
    2. People mentioned in context
    3. spaCy PERSON entities (strict filtering)
    """

    people = []

    IGNORE = {
        "WITNESSETH",
        "WHEREAS",
        "WHEREOF",
        "HEREBY",
        "HEREIN",
        "HERETO",
        "NOW",
        "THEREFORE",
        "SELLER",
        "BUYER",
        "PARTY",
        "CAP",
        "AGREEMENT",
        "PRODUCTS",
        "INITIAL TERM"
    }

    # -------------------------------------------------
    # 1. Signature Block
    # Only capture the current line after Name:
    # -------------------------------------------------

    for match in re.finditer(
        r"Name\s*:\s*([^\n\r]+)",
        text,
        re.IGNORECASE
    ):

        name = match.group(1).strip()

        # Remove accidental extra spaces
        name = " ".join(name.split())

        if len(name.split()) < 2:
            continue

        if name.upper() in IGNORE:
            continue

        people.append(name)

    # -------------------------------------------------
    # 2. Context based extraction
    # Example:
    # Under the supervision of Pyarelal Singh
    # -------------------------------------------------

    context_patterns = [

        r"under\s+the\s+supervision\s+of\s+([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+)+)",

        r"prepared\s+by\s+([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+)+)",

        r"reviewed\s+by\s+([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+)+)",

        r"approved\s+by\s+([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+)+)",

        r"drafted\s+by\s+([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+)+)",

        r"executed\s+by\s+([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+)+)",

        r"signed\s+by\s+([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+)+)",

        r"authori[sz]ed\s+signatory\s*[:-]?\s*([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+)+)",

        r"authorised\s+representative\s*[:-]?\s*([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+)+)",

        r"authorized\s+representative\s*[:-]?\s*([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+)+)",

        r"witness(?:ed)?\s+by\s+([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+)+)",

        r"attested\s+by\s+([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+)+)",

        r"certified\s+by\s+([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+)+)",

    ]

    for pattern in context_patterns:

        for match in re.finditer(pattern, text, re.IGNORECASE):

            person = " ".join(match.group(1).split()).strip()

            if len(person.split()) < 2:
                continue

            if person.upper() in IGNORE:
                continue

            people.append(person)

    # -------------------------------------------------
    # 3. spaCy fallback
    # -------------------------------------------------

    for ent in doc.ents:

        if ent.label_ != "PERSON":
            continue

        person = " ".join(ent.text.split()).strip()

        if len(person.split()) < 2:
            continue

        if person.upper() in IGNORE:
            continue

        # Ignore partial names
        if any(person.lower() in p.lower() for p in people):
            continue

        people.append(person)

    return unique(people)


def extract_dates_old(text):
    dates=DATE_RE.findall(text)
    full=[m.group(0) for m in DATE_RE.finditer(text)]
    effective=[]
    expiry=[]
    m=re.search(r"effective as of\s+("+DATE_RE.pattern+r")",text,re.I)
    if m: effective=[m.group(1)]
    m=re.search(r"until\s+("+DATE_RE.pattern+r")",text,re.I)
    if m: expiry=[m.group(1)]
    return {"EFFECTIVE DATE":effective,"EXPIRY DATE":expiry,"DATES":unique(full)}

def extract_dates(text):

    full = []

    date_patterns = [

        # July 18, 2026
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}",

        # 18 July 2026
        r"\d{1,2}\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}",

        # 18th July 2026
        r"\d{1,2}(?:st|nd|rd|th)\s+(January|February|March|April|May|June|July|August|September|October|November|December),?\s+\d{4}",

        # 18th day of July, 2026
        r"\d{1,2}(?:st|nd|rd|th)\s+day\s+of\s+(January|February|March|April|May|June|July|August|September|October|November|December),?\s+\d{4}",

        # this 18th day of July, 2026
        r"this\s+\d{1,2}(?:st|nd|rd|th)\s+day\s+of\s+(January|February|March|April|May|June|July|August|September|October|November|December),?\s+\d{4}",

    ]

    for pattern in date_patterns:

        for match in re.finditer(pattern, text, re.IGNORECASE):

            full.append(match.group())

    full = unique(full)

    effective = []
    expiry = []

    effective_patterns = [

        r"effective\s+as\s+of\s+(.*?)(?:,|\(|\n)",

        r"made\s+effective\s+as\s+of\s+(.*?)(?:,|\(|\n)",

        r"effective\s+date\s*[:\-]?\s*(.*?)(?:\n|$)",

        r"commence(?:s|d)?\s+on\s+(.*?)(?:,|\.|\n)",

    ]

    for pattern in effective_patterns:

        m = re.search(pattern, text, re.IGNORECASE)

        if m:

            value = m.group(1).strip()

            if any(month in value.lower() for month in [
                "january","february","march","april","may","june",
                "july","august","september","october","november","december"
            ]):

                effective.append(value)

                break

    m = re.search(
        r"(?:until|expire(?:s|d)?\s+on|termination\s+date\s*[:\-]?)\s+(.*?)(?:,|\.|\n)",
        text,
        re.IGNORECASE
    )

    if m:

        expiry.append(m.group(1).strip())

    return {
        "EFFECTIVE DATE": unique(effective),
        "EXPIRY DATE": unique(expiry),
        "DATES": full
    }

def extract_money(text):
    """
    Extract monetary values from legal contracts.
    """

    money = []

    patterns = [

        # ₹10,000
        r"₹\s?\d[\d,]*(?:\.\d+)?",

        # Rs. 10,000 / Rs 10,000
        #r"Rs\.?\s?\d[\d,]*(?:\.\d+)?",
        r"\bRs\.?\s*\d[\d,]*(?:\.\d+)?\b"

        # INR 10,000
        r"INR\s?\d[\d,]*(?:\.\d+)?",

        # USD 5,000
        r"USD\s?\d[\d,]*(?:\.\d+)?",

        # EUR 1000
        r"EUR\s?\d[\d,]*(?:\.\d+)?",

        # GBP 500
        r"GBP\s?\d[\d,]*(?:\.\d+)?",

        # $5000
        r"\$\s?\d[\d,]*(?:\.\d+)?",

        # ₹ 5 lakh
        r"₹\s?\d+(?:\.\d+)?\s*(?:lakh|lakhs|crore|crores|million|billion)",

        # INR 5 lakh
        r"INR\s?\d+(?:\.\d+)?\s*(?:lakh|lakhs|crore|crores|million|billion)",

        # Rupees One Thousand
        r"(?:Indian\s+)?Rupees?\s+[A-Za-z\s-]+?(?:Only)?(?=[.,;\n]|$)",

        # One Thousand Rupees
        r"[A-Za-z\s-]+?\s+Rupees?(?:\s+Only)?(?=[.,;\n]|$)",

        # Five Million Dollars
        r"[A-Za-z\s-]+?\s+(?:Dollars|USD|Euros|Pounds)(?:\s+Only)?(?=[.,;\n]|$)"
    ]

    for pattern in patterns:

        for match in re.finditer(pattern, text, re.IGNORECASE):

            value = " ".join(match.group().split()).strip()

            # Ignore percentages
            if "%" in value:
                continue

            # Ignore section numbers
            if re.fullmatch(r"\d+\.\d+", value):
                continue

            money.append(value)

    return unique(money)

def extract_entities(text,nlp):
    doc=nlp(text)
    result=defaultdict(list)
    comps=extract_companies(text,doc)
    result["COMPANIES"]=comps
    result["PARTIES"]=extract_parties(text,comps)

    people = extract_people(text, doc)
    if people:
        result["PEOPLE"] = people

    d=extract_dates(text)
    for k,v in d.items():
        if v: result[k]=v

    
    money = extract_money(text)
    if money:
        result["MONETARY VALUES"] = money    

    return {k:v for k,v in result.items() if v}
