"""
report.py

Export Report: the summary, clauses, risks and obligations as one PDF, Word or Excel file.

build_blocks() decides what the report says, as a flat list of (kind, content) blocks.
render_pdf() and render_docx() only decide how a block looks, so the two formats
always contain the same text. render_xlsx() works from the analysis data instead,
as one table per section, since a spreadsheet is for sorting and filtering.

Block kinds: title, meta, h1, h2, h3, p, bullet, quote, note.
Content is a string, or a list of (text, is_bold) runs for mixed formatting.
"""

import html
import io
import re
from datetime import datetime

import docx
import fitz  # PyMuPDF
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from clauses import summarize_clauses
from obligations import group_by_party, count_by_type
from risks import risk_score, risk_level, count_by_severity

REPORT_TITLE = "Document Analysis Report"
PLURALS = {
    "Obligation": "Obligations",
    "Right": "Rights",
    "Prohibition": "Prohibitions",
    "Responsibility": "Responsibilities",
}
DISCLAIMER = (
    "This report was generated automatically by keyword and pattern matching. It can miss items "
    "or flag harmless wording, so it is not a substitute for review by a qualified lawyer."
)

# Word files are XML, and python-docx refuses these characters (PDFs can contain them)
ILLEGAL_XML_RE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff￾￿]")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def _clean(text):
    return " ".join(ILLEGAL_XML_RE.sub(" ", str(text)).split())


def _runs(content):
    """Content as (cleaned text, is_bold) runs, keeping the spaces between runs."""
    if isinstance(content, str):
        return [(_clean(content), False)]
    return [(ILLEGAL_XML_RE.sub(" ", text), bold) for text, bold in content]


# ---------------------------------------------------------------------------
# Report content
# ---------------------------------------------------------------------------

def _summary_blocks(summary):
    """The summary is Markdown: **bold** text and "- " bullets."""
    blocks = []
    for line in summary.split("\n"):
        line = line.strip()
        if not line:
            continue

        whole_bold = re.fullmatch(r"\*\*([^*]+)\*\*", line)
        if whole_bold:
            blocks.append(("h2", whole_bold.group(1)))
            continue

        kind = "bullet" if line.startswith("- ") else "p"
        line = line[2:] if kind == "bullet" else line
        # re.split with one group alternates plain text and the bold parts
        parts = BOLD_RE.split(line)
        blocks.append((kind, [(part, i % 2 == 1) for i, part in enumerate(parts) if part]))
    return blocks


def _clause_blocks(clauses):
    if not clauses:
        return [("p", "No legal clauses detected in this document.")]

    blocks = [("p", f"Found {len(clauses)} clauses across {len(summarize_clauses(clauses))} types.")]
    for c in clauses:
        title = c["type"]
        if c["heading"] and c["heading"].lower() != c["type"].lower():
            title += f" — {c['heading']}"
        blocks.append(("h2", title))
        blocks.append(("note", f"Importance: {c['importance']} · Match confidence: {c['confidence']:.0%}"))
        blocks.append(("p", c["text"]))
        if c["key_terms"]:
            blocks.append(("p", [("Key terms: ", True), (" · ".join(c["key_terms"]), False)]))
        if c["also"]:
            blocks.append(("note", "Also touches on: " + ", ".join(c["also"])))
    return blocks


def _risk_blocks(findings):
    if not findings:
        return [("p", "No significant legal risks detected.")]

    score = risk_score(findings)
    counts = count_by_severity(findings)
    blocks = [
        ("p", [("Overall risk: ", True), (f"{score}/100 ({risk_level(score)})", False)]),
        ("p", f"High: {counts['High']} · Medium: {counts['Medium']} · Low: {counts['Low']}"),
    ]

    for f in findings:
        title = f"[{f['severity']}] {f['title']}"
        if f["section"]:
            title += f" — {f['section']}"
        blocks.append(("h2", title))
        blocks.append(("note", f"{f['category']} · {f['kind']}"))
        if f["excerpt"]:
            blocks.append(("quote", f["excerpt"]))
        blocks.append(("p", [("Why it matters: ", True), (f["why"], False)]))
        blocks.append(("p", [("Suggested fix: ", True), (f["recommendation"], False)]))
    return blocks


def _obligation_line(item):
    action = _clean(item["action"])
    runs = [(action[:1].upper() + action[1:], False)]
    for label, key in (("Deadline", "deadline"), ("Condition", "condition"), ("Section", "section")):
        if item[key]:
            runs.append((" · ", False))
            runs.append((f"{label}: ", True))
            runs.append((_clean(item[key]), False))
    return runs


def _obligation_blocks(items):
    if not items:
        return [("p", "No obligations, rights or responsibilities detected in this document.")]

    type_counts = count_by_type(items)
    blocks = [("p", " · ".join(f"{PLURALS[kind]}: {n}" for kind, n in type_counts.items()))]

    for party, party_items in group_by_party(items).items():
        blocks.append(("h2", party))
        for kind in type_counts:
            of_kind = [i for i in party_items if i["type"] == kind]
            if of_kind:
                blocks.append(("h3", PLURALS[kind]))
                blocks.extend(("bullet", _obligation_line(i)) for i in of_kind)
    return blocks


def build_blocks(filename, summary, clauses, items, findings):
    """The whole report as blocks. Every section appears, even when nothing was found."""
    return [
        ("title", REPORT_TITLE),
        ("meta", f"Source file: {filename}"),
        ("meta", f"Generated: {datetime.now():%d %B %Y}"),
        ("note", DISCLAIMER),
        ("h1", "Summary"),
        *_summary_blocks(summary),
        ("h1", "Clauses"),
        *_clause_blocks(clauses),
        ("h1", "Risks"),
        *_risk_blocks(findings),
        ("h1", "Obligations & Rights"),
        *_obligation_blocks(items),
    ]


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

PDF_CSS = """
body { margin: 0; font-family: sans-serif; font-size: 10pt; line-height: 1.4; color: #1f2937; }
h1 { font-size: 15pt; color: #3730a3; margin-top: 18pt; margin-bottom: 6pt; }
h2 { font-size: 11.5pt; color: #111827; margin-top: 12pt; margin-bottom: 3pt; }
h3 { font-size: 10pt; color: #374151; margin-top: 7pt; margin-bottom: 2pt; }
p { margin-top: 0; margin-bottom: 5pt; }
ul { margin-top: 0; margin-bottom: 5pt; }
li { margin-bottom: 3pt; }
.title { font-size: 21pt; font-weight: bold; color: #3730a3; margin-bottom: 8pt; }
.meta { color: #4b5563; margin-bottom: 1pt; }
.note { font-size: 8.5pt; color: #6b7280; }
.quote { font-style: italic; color: #4b5563; margin-left: 14pt; }
"""
PDF_MARGIN = 54
CHUNK_GAP = 0                 # points between chunks; the margins in PDF_CSS already space them
MAX_CHUNK_CHARS = 1500        # a chunk this size always fits on one page
MEASURE_HEIGHT = 100000       # tall enough to measure any chunk without it being cut
KEEP_WITH_NEXT = {"title", "meta", "note", "h1", "h2", "h3"}


def _html_inline(content):
    return "".join(
        f"<b>{html.escape(text)}</b>" if bold else html.escape(text)
        for text, bold in _runs(content)
    )


def _blocks_to_html(blocks):
    out = []
    in_list = False
    for kind, content in blocks:
        if kind == "bullet" and not in_list:
            out.append("<ul>")
        elif kind != "bullet" and in_list:
            out.append("</ul>")
        in_list = kind == "bullet"

        body = _html_inline(content)
        if kind == "bullet":
            out.append(f"<li>{body}</li>")
        elif kind in ("h1", "h2", "h3"):
            out.append(f"<{kind}>{body}</{kind}>")
        elif kind == "p":
            out.append(f"<p>{body}</p>")
        else:
            out.append(f'<p class="{kind}">{body}</p>')

    if in_list:
        out.append("</ul>")
    return "".join(out)


def _split_long(content):
    """Break very long text into page-safe pieces, at a sentence end where possible."""
    runs = _runs(content)
    if sum(len(text) for text, _ in runs) <= MAX_CHUNK_CHARS:
        return [runs]

    pieces, current, size = [], [], 0
    for text, bold in runs:
        for word in re.findall(r"\S+\s*", text):
            current.append((word, bold))
            size += len(word)
            sentence_end = word.rstrip()[-1] in ".;:"
            if size >= MAX_CHUNK_CHARS * 1.5 or (size >= MAX_CHUNK_CHARS and sentence_end):
                pieces.append(current)
                current, size = [], 0
    if current:
        pieces.append(current)
    return pieces


def _chunks(blocks):
    """Groups that stay on one page: a heading never sits apart from the text below it."""
    chunk, size = [], 0
    for kind, content in blocks:
        for piece in _split_long(content):
            piece_size = sum(len(text) for text, _ in piece)
            if chunk and size + piece_size > MAX_CHUNK_CHARS:
                yield chunk
                chunk, size = [], 0

            chunk.append((kind, piece))
            size += piece_size
            if kind not in KEEP_WITH_NEXT:
                yield chunk
                chunk, size = [], 0
    if chunk:
        yield chunk


def render_pdf(blocks):
    page = fitz.paper_rect("a4")
    area = page + (PDF_MARGIN, PDF_MARGIN, -PDF_MARGIN, -PDF_MARGIN)
    measure_area = fitz.Rect(area.x0, 0, area.x1, MEASURE_HEIGHT)

    buffer = io.BytesIO()
    writer = fitz.DocumentWriter(buffer)
    device = writer.begin_page(page)
    y = area.y0

    # One short story per chunk, with page breaks decided here. A single story left to
    # flow across pages can lay out past the bottom edge, which silently loses that text.
    for chunk in _chunks(blocks):
        story = fitz.Story(_blocks_to_html(chunk), user_css=PDF_CSS)
        _, filled = story.place(measure_area)
        height = filled[3]
        story.reset()

        if y > area.y0 and y + height > area.y1:
            writer.end_page()
            device = writer.begin_page(page)
            y = area.y0

        more = True
        while more:
            more, filled = story.place(fitz.Rect(area.x0, y, area.x1, area.y1))
            story.draw(device)
            y = filled[3] + CHUNK_GAP
            if more:                         # only a chunk taller than a whole page
                writer.end_page()
                device = writer.begin_page(page)
                y = area.y0

    writer.end_page()
    writer.close()

    # the stories can't number the pages, so that is done afterwards
    pdf = fitz.open(stream=buffer.getvalue(), filetype="pdf")
    for i, pdf_page in enumerate(pdf, start=1):
        label = f"Page {i} of {len(pdf)}"
        x = page.width - PDF_MARGIN - fitz.get_text_length(label, fontsize=8)
        pdf_page.insert_text((x, page.height - 30), label, fontsize=8, color=(0.42, 0.45, 0.5))
    pdf.set_metadata({"title": REPORT_TITLE})
    return pdf.tobytes(garbage=3, deflate=True)


# ---------------------------------------------------------------------------
# Word
# ---------------------------------------------------------------------------

DOCX_STYLES = {"h1": "Heading 1", "h2": "Heading 2", "h3": "Heading 3",
               "title": "Title", "bullet": "List Bullet", "quote": "Quote"}
NOTE_COLOR = RGBColor(0x6B, 0x72, 0x80)


def _add_field(paragraph, instruction):
    """A field Word fills in itself when it opens the file, such as the page number."""
    run = paragraph.add_run()
    for tag, text in (("begin", None), (None, instruction), ("end", None)):
        if tag:
            element = OxmlElement("w:fldChar")
            element.set(qn("w:fldCharType"), tag)
        else:
            element = OxmlElement("w:instrText")
            element.text = text
        run._r.append(element)


def render_docx(blocks):
    document = docx.Document()
    document.styles["Normal"].font.name = "Calibri"
    document.styles["Normal"].font.size = Pt(11)
    document.core_properties.title = REPORT_TITLE

    for kind, content in blocks:
        paragraph = document.add_paragraph(style=DOCX_STYLES.get(kind))
        for text, bold in _runs(content):
            run = paragraph.add_run(text)
            run.bold = bold or None
            if kind == "note":
                run.font.size = Pt(9)
                run.font.color.rgb = NOTE_COLOR

    footer = document.sections[0].footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    footer.add_run("Page ")
    _add_field(footer, "PAGE")
    footer.add_run(" of ")
    _add_field(footer, "NUMPAGES")

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------
# A spreadsheet is for sorting and filtering, so this renders the analysis as tables
# (one sheet per section) instead of the flowing blocks used by the PDF and Word files.

XLSX_MAX_CELL = 32767         # Excel's limit on characters in one cell
XLSX_HEADER_FILL = PatternFill("solid", fgColor="3730A3")
XLSX_HEADER_FONT = Font(bold=True, color="FFFFFF")
XLSX_WRAP = Alignment(wrap_text=True, vertical="top")
SEVERITY_FILLS = {
    "High": PatternFill("solid", fgColor="FECACA"),
    "Medium": PatternFill("solid", fgColor="FDE68A"),
    "Low": PatternFill("solid", fgColor="D1FAE5"),
}


def _cell_value(value):
    if isinstance(value, (int, float)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(v) for v in value)
    text = _clean(value)
    return text[:XLSX_MAX_CELL - 1] + "…" if len(text) > XLSX_MAX_CELL else text


def _set(cell, value):
    cell.value = _cell_value(value)
    if isinstance(cell.value, str) and cell.value.startswith("="):
        cell.data_type = "s"          # document text, never a formula


def _table_sheet(workbook, title, columns, rows, empty_message):
    """columns: [(header, width)]. rows: lists of values in column order."""
    sheet = workbook.create_sheet(title)
    if not rows:
        _set(sheet["A1"], empty_message)
        sheet.column_dimensions["A"].width = 80
        return sheet

    for col, (header, width) in enumerate(columns, start=1):
        cell = sheet.cell(row=1, column=col, value=header)
        cell.fill = XLSX_HEADER_FILL
        cell.font = XLSX_HEADER_FONT
        cell.alignment = XLSX_WRAP
        sheet.column_dimensions[get_column_letter(col)].width = width

    for r, values in enumerate(rows, start=2):
        for col, value in enumerate(values, start=1):
            cell = sheet.cell(row=r, column=col)
            _set(cell, value)
            cell.alignment = XLSX_WRAP

    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    return sheet


def _overview_sheet(sheet, filename, summary, clauses, items, findings):
    sheet.title = "Overview"
    sheet.column_dimensions["A"].width = 24
    sheet.column_dimensions["B"].width = 100

    def add(label="", value="", bold=False, size=None, color=None):
        sheet.append([None, None])
        row = sheet.max_row
        _set(sheet.cell(row=row, column=1), label)
        _set(sheet.cell(row=row, column=2), value)
        sheet.cell(row=row, column=1).font = Font(bold=True, size=size, color=color)
        sheet.cell(row=row, column=2).font = Font(bold=bold, color=color)
        sheet.cell(row=row, column=2).alignment = XLSX_WRAP
        sheet.cell(row=row, column=1).alignment = Alignment(vertical="top")

    sheet["A1"] = REPORT_TITLE
    sheet["A1"].font = Font(bold=True, size=18, color="3730A3")
    add()
    add("Source file", filename)
    add("Generated", f"{datetime.now():%d %B %Y}")
    add("Note", DISCLAIMER, color="6B7280")

    add()
    add("At a glance", size=13, color="3730A3")
    if findings:
        score = risk_score(findings)
        counts = count_by_severity(findings)
        add("Overall risk", f"{score}/100 ({risk_level(score)})", bold=True)
        add("Risks found", f"High: {counts['High']} · Medium: {counts['Medium']} · Low: {counts['Low']}")
    else:
        add("Overall risk", "No significant legal risks detected.")
    add("Clauses found", f"{len(clauses)} across {len(summarize_clauses(clauses))} types" if clauses else 0)
    if items:
        add("Obligations & rights",
            " · ".join(f"{PLURALS[kind]}: {n}" for kind, n in count_by_type(items).items()))
    else:
        add("Obligations & rights", 0)

    add()
    add("Summary", size=13, color="3730A3")
    for kind, content in _summary_blocks(summary):
        text = "".join(t for t, _ in _runs(content))
        if kind == "h2":
            add(value=text, bold=True)
        else:
            add(value=f"• {text}" if kind == "bullet" else text)


def render_xlsx(filename, summary, clauses, items, findings):
    workbook = Workbook()
    workbook.properties.title = REPORT_TITLE
    _overview_sheet(workbook.active, filename, summary, clauses, items, findings)

    clause_sheet = _table_sheet(
        workbook, "Clauses",
        [("Type", 22), ("Heading", 28), ("Importance", 12), ("Confidence", 12),
         ("Key terms", 30), ("Also touches on", 24), ("Text", 90)],
        [[c["type"], c["heading"], c["importance"], c["confidence"],
          c["key_terms"], c["also"], c["text"]] for c in clauses],
        "No legal clauses detected in this document.",
    )
    for row in clause_sheet.iter_rows(min_row=2, min_col=4, max_col=4):
        row[0].number_format = "0%"

    risk_sheet = _table_sheet(
        workbook, "Risks",
        [("Severity", 11), ("Title", 32), ("Section", 22), ("Category", 18), ("Kind", 16),
         ("Excerpt", 60), ("Why it matters", 50), ("Suggested fix", 50)],
        [[f["severity"], f["title"], f["section"], f["category"], f["kind"],
          f["excerpt"], f["why"], f["recommendation"]] for f in findings],
        "No significant legal risks detected.",
    )
    for row in risk_sheet.iter_rows(min_row=2, max_col=1):
        if row[0].value in SEVERITY_FILLS:
            row[0].fill = SEVERITY_FILLS[row[0].value]

    _table_sheet(
        workbook, "Obligations",
        [("Party", 22), ("Type", 16), ("Action", 70), ("Deadline", 22),
         ("Condition", 36), ("Section", 22)],
        [[party, i["type"], i["action"], i["deadline"], i["condition"], i["section"]]
         for party, party_items in group_by_party(items).items() for i in party_items],
        "No obligations, rights or responsibilities detected in this document.",
    )

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
