import streamlit as st
import streamlit.components.v1 as components

from utils import *
from summary import summarize_text
from entities2 import extract_entities
from keywords import extract_keywords
from qa2 import simple_qa, warm_up as warm_up_qa
from nlp_model import get_nlp, warm_up as warm_up_nlp
from classifier import classify_document
from Key_insights import extract_key_insights
from clauses import extract_clauses, summarize_clauses
from obligations import extract_obligations, group_by_party, count_by_type
from risks import analyze_risks, risk_score, risk_level, count_by_severity
from financials import extract_financial_terms, total_contract_value, count_by_category, format_money
from explainer import explain_clauses, average_scores, reading_level
from report import build_blocks, render_pdf, render_docx
import plotly.express as px

import base64
import csv
import html as html_lib
import re
from pathlib import Path
import mammoth
import fitz  # PyMuPDF
from PIL import Image
import io
from preprocessing import preprocess_text


# -------------------------------
# CONFIG
# -------------------------------
st.set_page_config(page_title="AI Document Analyzer", page_icon="📄", layout="wide")

# styling lives in style.css (presentation only)
st.markdown(
    f"<style>{(Path(__file__).parent / 'style.css').read_text(encoding='utf-8')}</style>",
    unsafe_allow_html=True,
)

# -------------------------------
# LOAD NLP MODEL
# -------------------------------
# Load the spaCy and Q&A models in background threads so the page renders immediately;
# get_nlp() / the Q&A model wait for the load only if they are needed before it finishes.
warm_up_nlp()
warm_up_qa()


@st.cache_data(show_spinner=False)
def cached_pdf_text(data):
    # Streamlit reruns this script on every click; OCR must not run again each time.
    return extract_text_from_pdf(data)


@st.cache_data
def cached_extract_clauses(text):
    return extract_clauses(text)


@st.cache_data
def cached_extract_obligations(text):
    return extract_obligations(text)


@st.cache_data
def cached_analyze_risks(text):
    return analyze_risks(text)


@st.cache_data
def cached_financial_terms(text):
    terms = extract_financial_terms(text)
    return terms, total_contract_value(terms, text)


@st.cache_data
def cached_explain_clauses(text):
    return explain_clauses(text)


# -------------------------------
# UI
# -------------------------------
st.markdown(
    """
    <div class="hero">
        <div class="hero-title">📄 AI Document Analyzer</div>
        <div class="hero-sub">Upload a contract or document and get clauses, obligations, risks and summaries in seconds.</div>
        <div class="chips">
            <span class="chip">⚖️ Clause extraction</span>
            <span class="chip">📋 Obligations &amp; rights</span>
            <span class="chip">🚨 Risk analysis</span>
            <span class="chip">❓ Q&amp;A</span>
            <span class="chip">🔒 Runs locally</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

uploaded_file = st.file_uploader(
    "📂 Upload PDF, DOCX, or Image",
    type=["pdf", "docx", "png", "jpg", "jpeg"]
)

# -------------------------------
# MAIN
# -------------------------------
if uploaded_file:

    with st.spinner("🔍 Extracting text..."):
        file_type = uploaded_file.name.split(".")[-1].lower()
        text = ""
        extraction_notes = []

        if file_type == "pdf":
            text, extraction_notes = cached_pdf_text(uploaded_file.getvalue())

        elif file_type == "docx":
            text = extract_text_from_docx(uploaded_file)

        elif file_type in ["png", "jpg", "jpeg"]:
            text = ocr_image(uploaded_file)

    # Advanced preprocessing (if you comment this you will lose preprocessing)
    text = preprocess_text(text)

    # Final normalization
    text = clean_text(text)

    for note in extraction_notes:
        st.warning(note)

    if not text:
        st.error("No readable text was found in this file, so there is nothing to analyze.")
        st.stop()

    st.markdown(
        f"""
        <div class="fileinfo">
            <span>📎</span>
            <span class="name">{html_lib.escape(uploaded_file.name)}</span>
            <span class="tag">{html_lib.escape(uploaded_file.name.split('.')[-1].upper())}</span>
            <span class="meta">{uploaded_file.size / 1024:,.1f} KB</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

#    col1, col2 = st.columns([2, 1])

#    with col1:
#        st.subheader("📜 Extracted Text")
        # st.text_area("Document Content", text, height=300)
#        st.text_area("Document Content", text, height=300)

#    with col2:
#        st.subheader("📊 Quick Stats")
#        st.write(f"**Words:** {len(text.split())}")
#        st.write(f"**Characters:** {len(text)}")


    # -------------------------------
    # DOCUMENT PREVIEW + TEXT
    # -------------------------------
    left, right = st.columns([1, 1])

    with left, st.container(border=True):
        st.markdown('<div class="panel-title">📄 Uploaded Document</div>', unsafe_allow_html=True)

        file_type = uploaded_file.name.split(".")[-1].lower()

        if file_type == "pdf":

            uploaded_file.seek(0)

            pdf = fitz.open(stream=uploaded_file.read(), filetype="pdf")

            html = """
            <div style="
                height:700px;
                overflow-y:auto;
                border:1px solid #ddd;
                padding:10px;
                background:#f8f9fa;">
            """

            for page in pdf:
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img_bytes = pix.tobytes("png")
                img_base64 = base64.b64encode(img_bytes).decode()

                html += f"""
                <img src="data:image/png;base64,{img_base64}"
                    style="width:100%; margin-bottom:15px; border:1px solid #ccc;">
                """

            html += "</div>"

            components.html(html, height=720)

        elif file_type in ["png", "jpg", "jpeg"]:
            st.image(uploaded_file, width="stretch")

        elif file_type == "docx":

            uploaded_file.seek(0)

            result = mammoth.convert_to_html(uploaded_file)
            html = result.value

            components.html(
                f"<div style=\"font-family:Georgia,serif;line-height:1.65;padding:12px 16px;color:#1f2937\">{html}</div>",
                height=700,
                scrolling=True,
            )

    with right, st.container(border=True):
        st.markdown('<div class="panel-title">📜 Extracted Text</div>', unsafe_allow_html=True)
        st.text_area("Document Content", text, height=700, label_visibility="collapsed")


    # Document stats section
    word_count = len(text.split())
    sentence_count = len(re.findall(r"[.!?]+(?:\s|$)", text))
    reading_minutes = max(1, round(word_count / 200))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📝 Words", f"{word_count:,}")
    c2.metric("🔤 Characters", f"{len(text):,}")
    c3.metric("📃 Sentences", f"{sentence_count:,}")
    c4.metric("⏱️ Reading time", f"{reading_minutes} min")

    st.write("")

    # EXPORT REPORT
    # always the complete analysis; the filters inside the tabs don't apply here
    export_clauses = cached_extract_clauses(text)
    export_items = cached_extract_obligations(text)
    export_findings = cached_analyze_risks(text)

    def report_blocks():
        summary = summarize_text(text, get_nlp())
        return build_blocks(uploaded_file.name, summary, export_clauses, export_items, export_findings)

    report_stem = Path(uploaded_file.name).stem

    with st.container(border=True):
        st.markdown('<div class="panel-title">📥 Export Report</div>', unsafe_allow_html=True)
        st.caption("Download the summary, clauses, risks and obligations as one file.")

        # callable data: the file is only built when a button is clicked
        d1, d2 = st.columns(2)
        d1.download_button(
            "⬇️ Download PDF",
            data=lambda: render_pdf(report_blocks()),
            file_name=f"{report_stem}_report.pdf",
            mime="application/pdf",
            on_click="ignore",
            width="stretch",
        )
        d2.download_button(
            "⬇️ Download Word",
            data=lambda: render_docx(report_blocks()),
            file_name=f"{report_stem}_report.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            on_click="ignore",
            width="stretch",
        )

    st.write("")


    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10, tab11 = st.tabs(
        ["📌 Summary", "🏷️ Entities", "🔑 Keywords", "❓ Q&A", "📂 Document Type", "💡 Key Insights",
         "⚖️ Clauses", "📋 Obligations & Rights", "🚨 Risk Analysis", "💰 Financial Terms",
         "🗣️ Plain English"]
    )

    # SUMMARY
    with tab1:
        if st.button("🧠 Generate Smart Summary", type="primary"):
            summary = summarize_text(text, get_nlp())
            with st.container(border=True):
                st.markdown(summary)

    # ENTITIES
#    with tab2:
#        entities = extract_entities(text, get_nlp())

#        grouped = {}
#        for ent, label in entities:
#            grouped.setdefault(label, []).append(ent)

#        for label, values in grouped.items():
#            st.markdown(f"### {label}")
#            for v in set(values):
#                st.write(f"- {v}")


    with tab2:

        entities = extract_entities(text, get_nlp())

        for category, values in entities.items():

            st.markdown(f"### {category}")

            for value in values:

                st.write(f"- {value}")

    # KEYWORDS
    with tab3:
        keywords = extract_keywords(text)
        st.markdown(
            '<div class="chips">'
            + "".join(
                f'<span class="chip" style="background:#eef2ff;color:#3730a3;border-color:#c7d2fe;'
                f'font-size:0.95rem;padding:0.3rem 0.9rem">{html_lib.escape(str(k))}</span>'
                for k in keywords
            )
            + "</div>",
            unsafe_allow_html=True,
        )

    # QA
    with tab4:
        question = st.text_input(
            "Type your question",
            placeholder="e.g. What is the notice period for termination?",
        )
        if question:
            answer = simple_qa(text, question)
            st.write(answer)

    # DOCUMENT CLASSIFICATION
    with tab5:
        if st.button("📂 Classify Document", type="primary"):
            category, scores = classify_document(text)
            st.success(f"Detected Document Type: **{category}**")
            st.subheader("Confidence Scores")

            for k, v in scores.items():
                st.write(f"**{k}** → {v}")


    # KEY INSIGHTS
    with tab6:
        if st.button("💡 Generate Key Insights", type="primary"):

            insights = extract_key_insights(text)

            st.subheader("Key Insights")

            if insights:
                for insight in insights:
                    st.write(f"• {insight}")
            else:
                st.info("No major insights detected.")

    # CLAUSE EXTRACTION
    with tab7:
        clauses = cached_extract_clauses(text)

        if not clauses:
            st.info("No legal clauses detected in this document.")
        else:
            counts = summarize_clauses(clauses)
            st.success(f"Found **{len(clauses)}** clauses across **{len(counts)}** types")

            selected = st.multiselect(
                "Filter by clause type",
                options=list(counts.keys()),
                default=list(counts.keys()),
                format_func=lambda t: f"{t} ({counts[t]})",
            )

            badge = {"High": "🔴", "Medium": "🟠", "Low": "🟢"}

            for c in clauses:
                if c["type"] not in selected:
                    continue

                title = f"{badge[c['importance']]} {c['type']}"
                if c["heading"]:
                    title += f" — {c['heading']}"

                with st.expander(title):
                    st.write(c["text"])
                    st.caption(
                        f"Importance: **{c['importance']}** · Match confidence: {c['confidence']:.0%}"
                    )
                    if c["key_terms"]:
                        st.markdown("**Key terms:** " + " · ".join(f"`{t}`" for t in c["key_terms"]))
                    if c["also"]:
                        st.caption("Also touches on: " + ", ".join(c["also"]))

    # OBLIGATIONS, RIGHTS & RESPONSIBILITIES
    with tab8:
        items = cached_extract_obligations(text)

        if not items:
            st.info("No obligations, rights or responsibilities detected in this document.")
        else:
            type_counts = count_by_type(items)
            icons = {"Obligation": "📌", "Right": "✅", "Prohibition": "🚫", "Responsibility": "⚠️"}

            cols = st.columns(len(type_counts))
            for col, (kind, n) in zip(cols, type_counts.items()):
                col.metric(f"{icons[kind]} {kind.replace('Responsibility', 'Responsibilitie')}s", n)

            groups = group_by_party(items)

            f1, f2 = st.columns(2)
            with f1:
                chosen_types = st.multiselect(
                    "Filter by type", list(type_counts.keys()), default=list(type_counts.keys())
                )
            with f2:
                chosen_parties = st.multiselect(
                    "Filter by party", list(groups.keys()), default=list(groups.keys())
                )

            for party, party_items in groups.items():
                if party not in chosen_parties:
                    continue

                shown = [i for i in party_items if i["type"] in chosen_types]
                if not shown:
                    continue

                st.markdown(f"### 👤 {party}")

                for kind in type_counts:
                    of_kind = [i for i in shown if i["type"] == kind]
                    if not of_kind:
                        continue

                    st.markdown(f"**{icons[kind]} {kind.replace('Responsibility', 'Responsibilitie')}s**")

                    for i in of_kind:
                        line = f"- {i['action'][:1].upper() + i['action'][1:]}"
                        if i["deadline"]:
                            line += f" ⏱️ *{i['deadline']}*"
                        if i["condition"]:
                            line += f"  \n  _Condition: {i['condition']}_"
                        if i["section"]:
                            line += f"  \n  _Section: {i['section']}_"
                        st.markdown(line)

    # RISK ANALYSIS
    with tab9:
        findings = cached_analyze_risks(text)

        if not findings:
            st.success("No significant legal risks detected.")
        else:
            score = risk_score(findings)
            level = risk_level(score)
            sev_counts = count_by_severity(findings)
            sev_badge = {"High": "🔴", "Medium": "🟠", "Low": "🟡"}

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Overall risk", f"{score}/100", level, delta_color="off")
            m2.metric("🔴 High", sev_counts["High"])
            m3.metric("🟠 Medium", sev_counts["Medium"])
            m4.metric("🟡 Low", sev_counts["Low"])
            st.progress(score / 100)

            f1, f2 = st.columns(2)
            with f1:
                chosen_sev = st.multiselect(
                    "Severity", list(sev_counts.keys()), default=list(sev_counts.keys()), key="risk_sev"
                )
            with f2:
                chosen_kind = st.multiselect(
                    "Finding type",
                    ["Risky wording", "Missing protection"],
                    default=["Risky wording", "Missing protection"],
                    key="risk_kind",
                )

            for f in findings:
                if f["severity"] not in chosen_sev or f["kind"] not in chosen_kind:
                    continue

                title = f"{sev_badge[f['severity']]} {f['title']}"
                if f["section"]:
                    title += f" — {f['section']}"

                with st.expander(title):
                    st.caption(f"{f['severity']} · {f['category']} · {f['kind']}")
                    if f["excerpt"]:
                        st.markdown(f"> {f['excerpt']}")
                    st.markdown(f"**Why it matters:** {f['why']}")
                    st.markdown(f"**Suggested fix:** {f['recommendation']}")

            st.caption(
                "Automated keyword-based screening. It can miss risks or flag harmless wording, "
                "so it is not a substitute for review by a qualified lawyer."
            )

    # FINANCIAL TERMS
    with tab10:
        fin_terms, fin_totals = cached_financial_terms(text)

        if not fin_terms:
            st.info("No amounts, fees, penalties or interest rates detected in this document.")
        else:
            cat_counts = count_by_category(fin_terms)

            # headline cards: total value per currency, then counts
            cards = [
                (f"💰 Total contract value ({cur})", format_money(info["total"], cur),
                 "Stated in contract" if info["basis"] == "Stated" else "Estimated")
                for cur, info in fin_totals.items()
            ][:2]
            if not cards:
                cards.append(("💰 Total contract value", "Not found", "No fees or price detected"))
            cards += [
                ("🧾 Financial terms", str(len(fin_terms)), None),
                ("⚠️ Penalties", str(cat_counts.get("Penalty", 0)), None),
                ("📈 Interest / late fees", str(cat_counts.get("Interest", 0)), None),
            ]
            for col, (label, value, note) in zip(st.columns(len(cards)), cards):
                col.metric(label, value, note, delta_color="off")

            for cur, info in fin_totals.items():
                with st.expander(f"How the {cur} total was calculated ({info['basis'].lower()})"):
                    for label, value in info["components"]:
                        st.markdown(f"- {label}: **{format_money(value, cur)}**")
                    for note in info["notes"]:
                        st.caption(note)

            chosen_cats = st.multiselect(
                "Filter by category",
                options=list(cat_counts.keys()),
                default=list(cat_counts.keys()),
                format_func=lambda c: f"{c} ({cat_counts[c]})",
                key="fin_cats",
            )

            rows = [
                {
                    "Category": t["category"],
                    "Amount": t["amount"],
                    "Frequency": t["frequency"] or "-",
                    "Due / Timing": t["timing"] or "-",
                    "Payer": t["payer"] or "-",
                    "Section": t["section"] or "-",
                    "Clause text": t["sentence"],
                }
                for t in fin_terms
                if t["category"] in chosen_cats
            ]

            st.dataframe(
                rows,
                width="stretch",
                hide_index=True,
                column_config={
                    "Clause text": st.column_config.TextColumn(width="large"),
                    "Amount": st.column_config.TextColumn(width="small"),
                },
            )

            csv_buf = io.StringIO()
            if rows:
                writer = csv.DictWriter(csv_buf, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)
            st.download_button(
                "⬇️ Download as CSV",
                data=csv_buf.getvalue().encode("utf-8-sig"),
                file_name="financial_terms.csv",
                mime="text/csv",
                disabled=not rows,
            )

            st.caption(
                "Amounts are found by pattern matching. Check the source clause before relying on a figure, "
                "especially estimated totals."
            )

    # PLAIN-ENGLISH EXPLAINER
    with tab11:
        explained = cached_explain_clauses(text)

        if not explained:
            st.info("No clauses found to explain in this document.")
        else:
            score_before, score_after = average_scores(explained)

            m1, m2, m3 = st.columns(3)
            m1.metric("🗣️ Clauses explained", len(explained))
            m2.metric("📕 Original readability", f"{score_before:g}/100", reading_level(score_before), delta_color="off")
            m3.metric("📗 Plain-English readability", f"{score_after:g}/100", reading_level(score_after), delta_color="off")

            type_counts_plain = {}
            for c in explained:
                type_counts_plain[c["type"]] = type_counts_plain.get(c["type"], 0) + 1

            chosen_plain = st.multiselect(
                "Filter by clause type",
                options=list(type_counts_plain.keys()),
                default=list(type_counts_plain.keys()),
                format_func=lambda t: f"{t} ({type_counts_plain[t]})",
                key="plain_types",
            )

            def md_escape(s):
                # a pair of "$" in a clause would otherwise render as a LaTeX formula
                return s.replace("$", "\\$")

            for c in explained:
                if c["type"] not in chosen_plain:
                    continue

                title = c["type"]
                if c["heading"] and c["heading"].lower() != c["type"].lower():
                    title += f" — {c['heading'].title() if c['heading'].isupper() else c['heading']}"

                with st.expander(title):
                    st.info(c["meaning"])

                    plain_col, original_col = st.columns(2)
                    with plain_col:
                        st.markdown("**In plain English**")
                        st.markdown("\n".join(f"- {md_escape(p)}" for p in c["points"]))
                    with original_col:
                        st.markdown("**Original wording**")
                        st.markdown(f"> {md_escape(c['original'])}")

                    if c["terms"]:
                        st.markdown("**Legal terms explained**")
                        st.markdown("\n".join(f"- **{t}:** {d}" for t, d in c["terms"]))

            st.caption(
                "Rewritten automatically with word-substitution rules, to help you read the contract. "
                "Sentences keep the original figures, but the original wording is what legally counts. "
                "This is not legal advice."
            )

else:
    st.markdown(
        """
        <div class="features">
            <div class="feature"><div class="icon">⚖️</div><div class="ft">Clause extraction</div>
                <div class="fd">Finds termination, payment, liability, confidentiality and other key clauses.</div></div>
            <div class="feature"><div class="icon">📋</div><div class="ft">Obligations &amp; rights</div>
                <div class="fd">Shows who must, may or must not do what, with deadlines and conditions.</div></div>
            <div class="feature"><div class="icon">🚨</div><div class="ft">Risk analysis</div>
                <div class="fd">Flags risky wording and missing protections, with a 0-100 risk score.</div></div>
            <div class="feature"><div class="icon">❓</div><div class="ft">Ask your document</div>
                <div class="fd">Ask a question and get the most relevant passages back.</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("👆 Upload a PDF, DOCX or image above to begin. Your file is processed locally.")