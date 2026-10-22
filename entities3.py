import re
from collections import defaultdict
from spacy.matcher import Matcher
from datetime import datetime


# ==========================================================
# Ignore words that spaCy often wrongly classifies as entities
# ==========================================================

LEGAL_STOPWORDS = {
    "agreement",
    "party",
    "parties",
    "seller",
    "buyer",
    "effective date",
    "initial term",
    "products",
    "purchase orders",
    "purchase order",
    "price schedule",
    "po",
    "cap",
    "ex-works",
    "neither party",
    "either party",
    "section",
    "article",
    "schedule",
    "annexure",
    "appendix"
}


# ==========================================================
# Company suffixes
# ==========================================================

COMPANY_SUFFIXES = (
    "LIMITED",
    "PRIVATE LIMITED",
    "PVT LTD",
    "PVT. LTD.",
    "LLP",
    "L.L.P.",
    "INC",
    "INC.",
    "CORPORATION",
    "CORP",
    "COMPANY",
    "CO.",
    "PLC",
    "LTD"
)


# ==========================================================
# Helper Functions
# ==========================================================

def normalize(text):

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def clean_entity(text):

    text = normalize(text)

    text = text.strip(".,;:()[]{}")

    return text


def unique(values):

    seen = set()

    result = []

    for item in values:

        key = item.lower()

        if key not in seen:

            seen.add(key)

            result.append(item)

    return result


# ==========================================================
# spaCy Matcher
# ==========================================================

def create_matcher(nlp):

    matcher = Matcher(nlp.vocab)

    seller_pattern = [
        {"LOWER": "seller"}
    ]

    buyer_pattern = [
        {"LOWER": "buyer"}
    ]

    first_party = [
        {"LOWER": "first"},
        {"LOWER": "part"}
    ]

    second_party = [
        {"LOWER": "second"},
        {"LOWER": "part"}
    ]

    effective_date = [
        {"LOWER": "effective"},
        {"LOWER": "date"}
    ]

    governing_law = [
        {"LOWER": "governing"},
        {"LOWER": "law"}
    ]

    jurisdiction = [
        {"LOWER": "jurisdiction"}
    ]

    matcher.add("SELLER", [seller_pattern])
    matcher.add("BUYER", [buyer_pattern])
    matcher.add("FIRST_PARTY", [first_party])
    matcher.add("SECOND_PARTY", [second_party])
    matcher.add("EFFECTIVE_DATE", [effective_date])
    matcher.add("GOVERNING_LAW", [governing_law])
    matcher.add("JURISDICTION", [jurisdiction])

    return matcher


# ==========================================================
# Company Extraction
# ==========================================================

def extract_companies(doc):

    companies = []

    for ent in doc.ents:

        if ent.label_ != "ORG":
            continue

        name = clean_entity(ent.text)

        if not name:
            continue

        lower = name.lower()

        if lower in LEGAL_STOPWORDS:
            continue

        if any(suffix in name.upper() for suffix in COMPANY_SUFFIXES):

            companies.append(name)

    return unique(companies)


# ==========================================================
# Person Extraction
# ==========================================================

def extract_people(doc):

    people = []

    for ent in doc.ents:

        if ent.label_ != "PERSON":
            continue

        name = clean_entity(ent.text)

        if len(name) < 3:
            continue

        if name.lower() in LEGAL_STOPWORDS:
            continue

        people.append(name)

    return unique(people)


# ==========================================================
# Contact Extraction
# ==========================================================

def extract_contacts(text):

    emails = re.findall(
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        text
    )

    phones = re.findall(
        r"\+?\d[\d\-\s]{8,18}\d",
        text
    )

    return {
        "EMAIL": unique(emails),
        "PHONE": unique([normalize(x) for x in phones])
    }

# ==========================================================
# Date Patterns
# ==========================================================

MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|November|December"
)

DATE_PATTERN = (
    rf"(?:{MONTHS})\s+\d{{1,2}},\s+\d{{4}}"
)

DATE_REGEX = re.compile(DATE_PATTERN, re.IGNORECASE)

# ==========================================================
# Party Extraction
# ==========================================================

def extract_parties(text, companies):

    result = {
        "FIRST PARTY": [],
        "SECOND PARTY": []
    }

    lower = text.lower()

    # ------------------------------------------------------
    # Method 1
    # Company followed by Seller / Buyer
    # ------------------------------------------------------

    for company in companies:

        escaped = re.escape(company)

        seller_pattern = (
            escaped +
            r".{0,250}?referred to as.*?seller"
        )

        buyer_pattern = (
            escaped +
            r".{0,250}?referred to as.*?buyer"
        )

        if re.search(seller_pattern, text,
                     re.IGNORECASE | re.DOTALL):

            result["FIRST PARTY"].append(company)

        elif re.search(buyer_pattern, text,
                       re.IGNORECASE | re.DOTALL):

            result["SECOND PARTY"].append(company)

    # ------------------------------------------------------
    # Method 2
    # FIRST PART / SECOND PART
    # ------------------------------------------------------

    first = re.search(
        r"(.*?)FIRST\s+PART",
        text,
        re.IGNORECASE | re.DOTALL
    )

    if first:

        block = first.group(1)

        for company in companies:

            if company in block:

                result["FIRST PARTY"].append(company)

    second = re.search(
        r"(.*?)SECOND\s+PART",
        text,
        re.IGNORECASE | re.DOTALL
    )

    if second:

        block = second.group(1)

        for company in companies:

            if company in block:

                result["SECOND PARTY"].append(company)

    result["FIRST PARTY"] = unique(result["FIRST PARTY"])
    result["SECOND PARTY"] = unique(result["SECOND PARTY"])

    return result

# ==========================================================
# Date Extraction
# ==========================================================

def extract_dates(text):

    result = {
        "START DATE": [],
        "END DATE": [],
        "DATES": []
    }

    dates = DATE_REGEX.findall(text)

    result["DATES"] = unique(dates)

    # ---------------------------------------
    # Effective Date
    # ---------------------------------------

    patterns = [

        r"effective\s+as\s+of\s+(" + DATE_PATTERN + r")",

        r"effective\s+date\s*\(\s*(" + DATE_PATTERN + r")",

        r"commence[s]?\s+on.*?(" + DATE_PATTERN + r")",

        r"agreement\s+date.*?(" + DATE_PATTERN + r")"

    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE | re.DOTALL
        )

        if match:

            result["START DATE"].append(
                clean_entity(match.group(1))
            )

    # ---------------------------------------
    # End Date
    # ---------------------------------------

    end_patterns = [

        r"until\s+(" + DATE_PATTERN + r")",

        r"expire[s]?\s+on\s+(" + DATE_PATTERN + r")",

        r"termination\s+date.*?(" + DATE_PATTERN + r")",

        r"remain.*?until\s+(" + DATE_PATTERN + r")"

    ]

    for pattern in end_patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE | re.DOTALL
        )

        if match:

            result["END DATE"].append(
                clean_entity(match.group(1))
            )

    result["START DATE"] = unique(result["START DATE"])
    result["END DATE"] = unique(result["END DATE"])

    return result

# ==========================================================
# Contract Term
# ==========================================================

def extract_contract_term(text):

    result = []

    patterns = [

        r'Initial\s+Term',

        r'Renewal\s+Term',

        r'Term\s*:\s*(.*?)(?:\n|$)',

        r'shall\s+remain\s+in\s+full\s+force.*?until',

        r'shall\s+commence.*?until'

    ]

    for pattern in patterns:

        matches = re.finditer(
            pattern,
            text,
            re.IGNORECASE | re.DOTALL
        )

        for match in matches:
        
            value = clean_entity(match.group())

            if len(value) > 4:

                result.append(value)

    return unique(result)

# ==========================================================
# Governing Law
# ==========================================================

def extract_governing_law(text):

    laws = []

    patterns = [

        r"governed\s+by\s+(?:the\s+)?laws?\s+of\s+([A-Za-z\s]+?)(?:\.|,|\n)",

        r"governing\s+law\s*:\s*(.+?)(?:\n|$)",

        r"construed\s+in\s+accordance\s+with\s+the\s+laws?\s+of\s+([A-Za-z\s]+?)(?:\.|,)"

    ]

    for pattern in patterns:

        matches = re.finditer(
            pattern,
            text,
            re.IGNORECASE | re.DOTALL
        )

        for match in matches:

            law = clean_entity(match.group(1))

            if len(law) > 2:
                laws.append(law)

    return unique(laws)

# ==========================================================
# Jurisdiction
# ==========================================================

def extract_jurisdiction(text, doc):

    places = []

    #
    # Method 1
    # courts of ...
    #

    patterns = [

        r"courts?\s+of\s+([A-Za-z\s]+)",

        r"exclusive\s+jurisdiction\s+of\s+([A-Za-z\s]+)",

        r"jurisdiction\s+of\s+([A-Za-z\s]+)"

    ]

    for pattern in patterns:

        matches = re.finditer(
            pattern,
            text,
            re.IGNORECASE
        )

        for match in matches:

            value = clean_entity(match.group(1))

            places.append(value)

    #
    # Method 2
    # spaCy locations
    #

    for ent in doc.ents:

        if ent.label_ in ["GPE", "LOC"]:

            location = clean_entity(ent.text)

            if location.lower() not in LEGAL_STOPWORDS:

                places.append(location)

    return unique(places)

# ==========================================================
# Money Extraction
# ==========================================================

def extract_money(text, doc):

    money = []

    #
    # spaCy MONEY
    #

    for ent in doc.ents:

        if ent.label_ == "MONEY":

            money.append(clean_entity(ent.text))

    #
    # Regex
    #

    pattern = (
        r"(?:₹|Rs\.?|INR|USD|\$|EUR|€)\s?"
        r"[\d,]+(?:\.\d+)?"
    )

    regex_money = re.findall(
        pattern,
        text,
        re.IGNORECASE
    )

    money.extend(regex_money)

    return unique(money)

# ==========================================================
# Locations
# ==========================================================

def extract_locations(doc):

    locations = []

    for ent in doc.ents:

        if ent.label_ in ["GPE", "LOC"]:

            value = clean_entity(ent.text)

            if value.lower() in LEGAL_STOPWORDS:
                continue

            locations.append(value)

    return unique(locations)

# ==========================================================
# Master Function
# ==========================================================

def extract_entities(text, nlp):

    text = normalize(text)

    doc = nlp(text)

    companies = extract_companies(doc)

    contacts = extract_contacts(text)

    parties = extract_parties(text, companies)

    dates = extract_dates(text)

    result = defaultdict(list)

    #
    # Companies
    #

    result["COMPANIES"] = companies

    #
    # Parties
    #

    result["FIRST PARTY"] = parties["FIRST PARTY"]

    result["SECOND PARTY"] = parties["SECOND PARTY"]

    #
    # People
    #

    result["PERSON"] = extract_people(doc)

    #
    # Dates
    #

    result["START DATE"] = dates["START DATE"]

    result["END DATE"] = dates["END DATE"]

    result["DATE"] = dates["DATES"]

    #
    # Contract Term
    #

    result["TERM"] = extract_contract_term(text)

    #
    # Governing Law
    #

    result["GOVERNING LAW"] = extract_governing_law(text)

    #
    # Jurisdiction
    #

    result["JURISDICTION"] = extract_jurisdiction(
        text,
        doc
    )

    #
    # Locations
    #

    result["LOCATION"] = extract_locations(doc)

    #
    # Money
    #

    result["MONETARY VALUE"] = extract_money(
        text,
        doc
    )

    #
    # Contacts
    #

    result["EMAIL"] = contacts["EMAIL"]

    result["PHONE"] = contacts["PHONE"]

    #
    # Remove empty categories
    #

    final = {}

    for key, value in result.items():

        value = unique(value)

        if value:

            final[key] = value

    return final

