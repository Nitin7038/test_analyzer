import streamlit as st
import streamlit.components.v1 as components
import spacy

from utils import *
from summary import summarize_text
from entities2 import extract_entities
from keywords import extract_keywords
from qa2 import simple_qa
from classifier import classify_document
from Key_insights import extract_key_insights
import plotly.express as px

import base64
import mammoth
import fitz  # PyMuPDF
from PIL import Image
import io
from preprocessing import preprocess_text


# -------------------------------
# CONFIG
# -------------------------------
st.set_page_config(page_title="AI Document Analyzer", layout="wide")

# -------------------------------
# LOAD NLP MODEL
# -------------------------------
@st.cache_resource
def load_model():
    #return spacy.load("en_core_web_sm")
    return spacy.load("en_core_web_md")

nlp = load_model()

# -------------------------------
# UI
# -------------------------------
st.title("📄 AI Document Analyzer")
st.markdown("Upload a document and get **AI-powered insights** instantly 🚀")

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

    with left:
        st.subheader("📄 Uploaded Document")

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
                html,
                height=700,
                scrolling=True,
            )

    with right:
        st.subheader("📜 Extracted Text")
        st.text_area("Document Content", text, height=700)



    #Document stats section
    st.divider()

    st.subheader("📊 Quick Statistics")

    c1, c2 = st.columns(2)

    with c1:
        st.metric("Words", len(text.split()))

    with c2:
        st.metric("Characters", len(text))



    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
        ["📌 Summary", "🏷️ Entities", "🔑 Keywords", "❓ Q&A", "📂 Document Type", "💡 Key Insights"]
    )

    # SUMMARY
    with tab1:
        if st.button("🧠 Generate Smart Summary"):
            summary = summarize_text(text, nlp)
            st.write(summary)

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
        st.write(", ".join(keywords))

    # QA
    with tab4:
        question = st.text_input("Type your question")
        if question:
            answer = simple_qa(text, question)
            st.write(answer)

    # DOCUMENT CLASSIFICATION
    with tab5:
        if st.button("📂 Classify Document"):
            category, scores = classify_document(text)
            st.success(f"Detected Document Type: **{category}**")
            st.subheader("Confidence Scores")

            for k, v in scores.items():
                st.write(f"**{k}** → {v}")


    # KEY INSIGHTS
    with tab6:
        if st.button("💡 Generate Key Insights"):

            insights = extract_key_insights(text)

            st.subheader("Key Insights")

            if insights:
                for insight in insights:
                    st.write(f"• {insight}")
            else:
                st.info("No major insights detected.")



else:
    st.info("👆 Upload a document to begin analysis")