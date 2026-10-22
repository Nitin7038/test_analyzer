from collections import Counter
import re


def remove_non_printable(text):
    return "".join(
        ch for ch in text
        if ch.isprintable() or ch == "\n"
    )


def remove_page_numbers(text):
    lines = text.split("\n")
    cleaned = []

    for line in lines:
        line = line.strip()

        if re.fullmatch(r"\d+", line):
            continue

        cleaned.append(line)

    return "\n".join(cleaned)


def remove_duplicate_lines(text):
    seen = set()
    cleaned = []

    for line in text.split("\n"):
        line = line.strip()

        if line and line not in seen:
            seen.add(line)
            cleaned.append(line)

    return "\n".join(cleaned)


def remove_watermarks(text, threshold=5):
    lines = [
        line.strip()
        for line in text.split("\n")
        if line.strip()
    ]

    counts = Counter(lines)

    cleaned = []

    for line in lines:
        if counts[line] > threshold:
            continue

        cleaned.append(line)

    return "\n".join(cleaned)


def preprocess_text(text):
    """
    Apply advanced document preprocessing.
    """

    text = remove_non_printable(text)
    text = remove_page_numbers(text)
    text = remove_duplicate_lines(text)
    text = remove_watermarks(text)

    return text