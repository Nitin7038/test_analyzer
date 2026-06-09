import streamlit as st
import spacy

from utils import *
from summary import summarize_text
from entities import extract_entities
from keywords import extract_keywords
from qa import simple_qa
from classifier import classify_document
from Key_insights import extract_key_insights
from theme_extraction import extract_themes
import plotly.express as px

# -------------------------------
# CONFIG
# -------------------------------
st.set_page_config(page_title="AI Document Analyzer", layout="wide")

# -------------------------------
# LOAD NLP MODEL
# -------------------------------
@st.cache_resource
def load_model():
    return spacy.load("en_core_web_sm")

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

    text = clean_text(text)

    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("📜 Extracted Text")
        st.text_area("Document Content", text, height=300)

    with col2:
        st.subheader("📊 Quick Stats")
        st.write(f"**Words:** {len(text.split())}")
        st.write(f"**Characters:** {len(text)}")

    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(
        ["📌 Summary", "🏷️ Entities", "🔑 Keywords", "❓ Q&A", "📂 Document Type", "💡 Key Insights", "📚 Document Themes"]
    )

    # SUMMARY
    with tab1:
        if st.button("🧠 Generate Smart Summary"):
            summary = summarize_text(text, nlp)
            st.write(summary)

    # ENTITIES
    with tab2:
        entities = extract_entities(text, nlp)

        grouped = {}
        for ent, label in entities:
            grouped.setdefault(label, []).append(ent)

        for label, values in grouped.items():
            st.markdown(f"### {label}")
            for v in set(values):
                st.write(f"- {v}")

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


    # -----------------------------------
    # DOCUMENT THEMES
    # -----------------------------------

    with tab7:

        if st.button("📚 Discover Themes"):

            themes, df = extract_themes(text)

            st.subheader("📊 Theme Relevance")

            fig = px.bar(
                df,
                x="score",
                y="theme",
                orientation="h",
                text="score"
            )

            fig.update_traces(
                texttemplate="%{text:.1f}",
                textposition="outside"
            )

            fig.update_layout(
                height=500,
                yaxis=dict(autorange="reversed"),
                xaxis_title="Relevance Score",
                yaxis_title=""
            )

            st.plotly_chart(
                fig,
                use_container_width=True
            )

            st.markdown("---")

            st.subheader("📚 Detected Themes")

            for item in themes:

                st.markdown(
                    f"""
    ### 🎯 {item['theme']}

    **Relevance Score:** {item['score']:.1f}
    """
                )

                st.divider()




else:
    st.info("👆 Upload a document to begin analysis")