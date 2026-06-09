import re

def extract_entities(text, nlp):
    doc = nlp(text)

    entities = []

    # -------------------------------
    # 1. spaCy Named Entities
    # -------------------------------
    for ent in doc.ents:
        if ent.label_ in ["PERSON", "ORG", "GPE", "LOC", "DATE"]:
            entities.append((ent.text, ent.label_))

    # -------------------------------
    # 2. Email Extraction (Regex)
    # -------------------------------
    emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
    for email in emails:
        entities.append((email, "EMAIL"))

    # -------------------------------
    # 3. Phone Number Extraction
    # -------------------------------
    phones = re.findall(r'\+?\d[\d\s\-]{8,15}\d', text)
    for phone in phones:
        entities.append((phone.strip(), "PHONE"))

    # -------------------------------
    # 4. Remove Duplicates
    # -------------------------------
    entities = list(set(entities))

    return entities