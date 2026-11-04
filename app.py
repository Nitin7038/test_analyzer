import streamlit as st
import streamlit.components.v1 as components
import spacy

from utils import *
from summary import summarize_text
from entities2 import extract_entities
from keywords import extract_keywords
from qa2 import simple_qa, warm_up
from classifier import classify_document
from Key_insights import extract_key_insights
from clauses import extract_clauses, summarize_clauses
from obligations import extract_obligations, group_by_party, count_by_type
from risks import analyze_risks, risk_score, risk_level, count_by_severity
import plotly.express as px

import base64
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
@st.cache_resource
def load_model():
    #return spacy.load("en_core_web_sm")
    return spacy.load("en_core_web_md")

nlp = load_model()

# load the Q&A embedding model in the background so the first question isn't slow
warm_up()


@st.cache_data
def cached_extract_clauses(text):
    return extract_clauses(text)


@st.cache_data
def cached_extract_obligations(text):
    return extract_obligations(text)


@st.cache_data
def cached_analyze_risks(text):
    return analyze_risks(text)


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
        file_type = uploaded_file.name.split(".")[-1]
        text = ""

        if file_type == "pdf":
            text = extract_text_from_pdf(uploaded_file)

        elif file_type == "docx":
            text = extract_text_from_docx(uploaded_file)

        elif file_type in ["png", "jpg", "jpeg"]:
            text = ocr_image(uploaded_file)

    # Advanced preprocessing (if you comment this you will lose preprocessing)
    text = preprocess_text(text)

    # Final normalization
    text = clean_text(text)

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
            st.image(uploaded_file, use_container_width=True)

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



    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs(
        ["📌 Summary", "🏷️ Entities", "🔑 Keywords", "❓ Q&A", "📂 Document Type", "💡 Key Insights",
         "⚖️ Clauses", "📋 Obligations & Rights", "🚨 Risk Analysis"]
    )

    # SUMMARY
    with tab1:
        if st.button("🧠 Generate Smart Summary", type="primary"):
            summary = summarize_text(text, nlp)
            with st.container(border=True):
                st.markdown(summary)

    # ENTITIES
#    with tab2:
#        entities = extract_entities(text, nlp)

#        grouped = {}
#        for ent, label in entities:
#            grouped.setdefault(label, []).append(ent)

#        for label, values in grouped.items():
#            st.markdown(f"### {label}")
#            for v in set(values):
#                st.write(f"- {v}")


    with tab2:

        entities = extract_entities(text, nlp)

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