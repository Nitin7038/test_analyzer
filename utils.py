import math
import re
import statistics
from collections import Counter

import docx
import fitz  # PyMuPDF
import pytesseract
from PIL import Image

HEADER_FOOTER_BAND = 0.1      # top/bottom share of the page searched for running headers/footers
MIN_PAGE_CHARS = 25           # a page with an image and less text than this is treated as scanned
OCR_DPI = 300
PARAGRAPH_GAP = 1.3           # a line pitch this many times the normal one starts a new paragraph

PAGE_LABEL_RE = re.compile(r"^(?:page\s*)?\d+(?:\s*(?:of|/)\s*\d+)?$|^-\s*\d+\s*-$", re.I)
LIST_START_RE = re.compile(
    r"^(?:\(?[a-z0-9]{1,4}\)\s"                 # (a) / a) / (iv)
    r"|\d+[.)]\s|\d+(?:\.\d+)+[.)]?\s"          # 1. / 1) / 1.2
    r"|[•●▪◦*\-–]\s"                            # bullets
    r"|(?:ARTICLE|SECTION|CLAUSE|PART|SCHEDULE|ANNEXURE|APPENDIX|EXHIBIT)\s+[A-Z0-9]+\b)",
    re.I,
)
SENTENCE_END_RE = re.compile(r"(?:[.;:!?,]|\band|\bor)[\"')\]]*$", re.I)
TRAILING_HYPHEN_RE = re.compile(r"([A-Za-z]+)-$")

# "non-\nrenewal" is a real compound; "termi-\nnation" is only a line-break hyphen.
COMPOUND_PREFIXES = {
    "all", "anti", "co", "cross", "ex", "full", "high", "long", "low", "mid", "multi", "non",
    "part", "self", "semi", "short", "then", "third", "well",
}

# PDF fonts often encode a visible hyphen as a soft hyphen, and spaces as no-break spaces.
PDF_CHARS = str.maketrans({"­": "-", "‐": "-", "‑": "-", " ": " "})


def clean_text(text):
    # Normalize Windows line endings
    text = text.replace("\r", "")

    # Remove extra spaces and tabs only
    text = re.sub(r"[ \t]+", " ", text)

    # Remove excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


# ---------------------------------------------------------------------------
# PDF: page -> positioned lines
# ---------------------------------------------------------------------------

def _make_line(text, x0, y0, x1, y1, size, bold=False):
    return {"text": text, "x0": x0, "y0": y0, "x1": x1, "y1": y1, "size": size, "bold": bold}


def _native_lines(page):
    """Lines of a page's text layer. Ligatures are expanded; off-page text is clipped."""
    flags = fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_MEDIABOX_CLIP
    lines = []

    for block in page.get_text("dict", flags=flags)["blocks"]:
        for line in block.get("lines", []):
            if abs(line["dir"][1]) > 0.05:      # rotated: diagonal watermark or margin stamp
                continue

            spans = [s for s in line["spans"] if s["text"].strip()]
            text = " ".join("".join(s["text"] for s in line["spans"]).translate(PDF_CHARS).split())
            if not text:
                continue

            bold = all(s["flags"] & fitz.TEXT_FONT_BOLD or "bold" in s["font"].lower() for s in spans)
            lines.append(_make_line(text, *line["bbox"], max(s["size"] for s in spans), bold))

    return lines


def _ocr_lines(page):
    """OCR a scanned page into the same line format, in page coordinates (points)."""
    pix = page.get_pixmap(dpi=OCR_DPI, colorspace=fitz.csRGB, alpha=False)
    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    scale = 72 / OCR_DPI

    grouped = {}
    for i, word in enumerate(data["text"]):
        if word.strip() and float(data["conf"][i]) >= 0:
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            grouped.setdefault(key, []).append(i)

    lines = []
    for indices in grouped.values():
        x0 = min(data["left"][i] for i in indices) * scale
        y0 = min(data["top"][i] for i in indices) * scale
        x1 = max(data["left"][i] + data["width"][i] for i in indices) * scale
        y1 = max(data["top"][i] + data["height"][i] for i in indices) * scale
        text = " ".join(data["text"][i].strip() for i in indices)
        lines.append(_make_line(text, x0, y0, x1, y1, y1 - y0))

    return lines


# ---------------------------------------------------------------------------
# PDF: running headers / footers
# ---------------------------------------------------------------------------

def _in_margin_band(line, page_height):
    band = page_height * HEADER_FOOTER_BAND
    return line["y1"] <= band or line["y0"] >= page_height - band


def _repeat_key(line):
    return re.sub(r"\d+", "#", line["text"].lower())


def _remove_headers_footers(pages):
    """Drop page labels and any margin line repeated on at least half of the pages."""
    seen = Counter()
    for lines, height in pages:
        seen.update({_repeat_key(l) for l in lines if _in_margin_band(l, height)})

    needed = max(2, math.ceil(len(pages) / 2))
    repeated = {key for key, count in seen.items() if count >= needed}

    def is_furniture(line, height):
        if not _in_margin_band(line, height):
            return False
        if PAGE_LABEL_RE.match(line["text"]):
            return True
        return _repeat_key(line) in repeated and not LIST_START_RE.match(line["text"])

    return [([l for l in lines if not is_furniture(l, height)], height) for lines, height in pages]


# ---------------------------------------------------------------------------
# PDF: reading order
# ---------------------------------------------------------------------------

def _column_gutter(lines, page_width):
    """x position between two prose columns, or None for a single-column page."""
    best_x, best_hits = None, len(lines)

    for x in range(int(page_width * 0.3), int(page_width * 0.7), 4):
        hits = sum(1 for l in lines if l["x0"] < x < l["x1"])
        closer = best_x is None or abs(x - page_width / 2) < abs(best_x - page_width / 2)
        if hits < best_hits or (hits == best_hits and closer):
            best_x, best_hits = x, hits

    if best_x is None or best_hits > len(lines) * 0.25:
        return None

    left = [l for l in lines if l["x1"] <= best_x]
    right = [l for l in lines if l["x0"] >= best_x]
    if min(len(left), len(right)) < 5:
        return None

    # Prose fills the space beside the gutter; table cells do not, and must stay in rows.
    left_space = best_x - min(l["x0"] for l in left)
    right_space = max(l["x1"] for l in right) - best_x
    for side, space in ((left, left_space), (right, right_space)):
        if statistics.median(l["x1"] - l["x0"] for l in side) < space * 0.6:
            return None

    return best_x


def _merge_rows(lines):
    """Sort top to bottom, joining cells that sit on the same visual row."""
    rows = []

    for line in sorted(lines, key=lambda l: (round(l["y0"]), l["x0"])):
        row = rows[-1] if rows else None
        same_row = row and min(row["y1"], line["y1"]) - max(row["y0"], line["y0"]) > line["size"] * 0.5
        if same_row and line["x0"] >= row["x1"] - 1:
            row.update(text=f"{row['text']} {line['text']}", x1=line["x1"],
                       y1=max(row["y1"], line["y1"]), bold=row["bold"] and line["bold"])
        else:
            rows.append(dict(line))

    return rows


def _reading_order(lines, page_width):
    """Lines in reading order, each tagged with the right edge of its column."""
    if not lines:
        return []

    def tagged(group):
        rows = _merge_rows(group)
        if rows:
            # A high percentile, so one over-wide line does not move the column edge.
            edges = sorted(r["x1"] for r in rows)
            right = edges[int(len(edges) * 0.8)]
            for r in rows:
                r["right"] = right
        return rows

    gutter = _column_gutter(lines, page_width)
    if gutter is None:
        return tagged(lines)

    left = [l for l in lines if l["x1"] <= gutter]
    right = [l for l in lines if l["x0"] >= gutter]
    spanning = sorted((l for l in lines if l["x0"] < gutter < l["x1"]), key=lambda l: l["y0"])

    # Full-width lines (a title, say) divide the page into bands of two columns each.
    ordered = []
    top = -math.inf
    for divider in spanning + [None]:
        bottom = divider["y0"] if divider else math.inf
        for side in (left, right):
            ordered += tagged([l for l in side if top <= l["y0"] < bottom])
        if divider:
            ordered += tagged([divider])
            top = divider["y0"]

    return ordered


# ---------------------------------------------------------------------------
# PDF: lines -> paragraphs
# ---------------------------------------------------------------------------

def _ends_sentence(text):
    return bool(SENTENCE_END_RE.search(text))


def _wrapped(a, b):
    """True if the first word of b would not have fitted on line a, i.e. a really was wrapped."""
    average_char_width = b["size"] * 0.5
    word_width = (len(b["text"].split()[0]) + 1) * average_char_width
    return a["x1"] + word_width >= a["right"]


def _continues(a, b, pitch):
    """Does line b carry on the paragraph that line a belongs to?"""
    if a["bold"] != b["bold"] or abs(a["size"] - b["size"]) > 1 or not _wrapped(a, b):
        return False

    if a.get("page") != b.get("page") or b["y0"] <= a["y0"]:       # moved to a new page or column
        return not _ends_sentence(a["text"])

    if b["y0"] - a["y0"] > pitch * PARAGRAPH_GAP:
        return False

    if _ends_sentence(a["text"]):
        if LIST_START_RE.match(b["text"]):
            return False
        if b["x0"] > a["x0"] + b["size"]:                           # indented first line
            return False

    return True


def _join_lines(left, right):
    """Join two wrapped lines, undoing a line-break hyphen."""
    match = TRAILING_HYPHEN_RE.search(left)
    if match and right[:1].islower() and match.group(1).lower() not in COMPOUND_PREFIXES:
        return left[:-1] + right
    if left.endswith("-") and match:
        return left + right
    return f"{left} {right}"


def _paragraphs(lines):
    pitches = [
        b["y0"] - a["y0"] for a, b in zip(lines, lines[1:])
        if a.get("page") == b.get("page") and b["y0"] > a["y0"]
    ]
    pitch = statistics.median(pitches) if pitches else math.inf

    paragraphs = []
    previous = None

    for line in lines:
        if previous and _continues(previous, line, pitch):
            paragraphs[-1] = _join_lines(paragraphs[-1], line["text"])
        else:
            paragraphs.append(line["text"])
        previous = line

    return paragraphs


def extract_text_from_pdf(data):
    """
    Text of a PDF as one logical paragraph per line (the same shape DOCX extraction gives).

    Returns (text, notes). notes are user-facing messages about the extraction.
    Pages with no usable text layer are read with OCR.
    """
    pages = []
    widths = []
    ocr_pages = []
    skipped = 0

    with fitz.open(stream=data, filetype="pdf") as pdf:
        for page in pdf:
            lines = _native_lines(page)
            chars = sum(len(l["text"]) for l in lines)

            if chars < MIN_PAGE_CHARS and page.get_images():
                try:
                    lines = _ocr_lines(page)
                    ocr_pages.append(page.number + 1)
                except pytesseract.TesseractNotFoundError:
                    skipped += 1

            pages.append((lines, page.rect.height))
            widths.append(page.rect.width)

    all_lines = []
    for number, (lines, _) in enumerate(_remove_headers_footers(pages)):
        for line in _reading_order(lines, widths[number]):
            line["page"] = number
            all_lines.append(line)

    notes = []
    if ocr_pages:
        notes.append(f"{len(ocr_pages)} scanned page(s) were read with OCR. "
                     "Check important figures against the original.")
    if skipped:
        notes.append(f"{skipped} scanned page(s) could not be read because Tesseract OCR is not "
                     "installed, so the analysis below does not cover them.")

    return "\n".join(_paragraphs(all_lines)), notes


def extract_text_from_docx(file):
    doc = docx.Document(file)
    return "\n".join([para.text for para in doc.paragraphs])

def ocr_image(file):
    image = Image.open(file)
    return pytesseract.image_to_string(image)
