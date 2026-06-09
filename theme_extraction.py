from keybert import KeyBERT
import pandas as pd

# Load once
kw_model = KeyBERT()

def extract_themes(text, top_n=8):

    keywords = kw_model.extract_keywords(
        text,
        keyphrase_ngram_range=(1, 3),
        stop_words="english",
        use_maxsum=True,
        nr_candidates=20,
        top_n=top_n
    )

    themes = []

    for phrase, score in keywords:
        themes.append({
            "theme": phrase.title(),
            "score": round(score * 100, 2)
        })

    df = pd.DataFrame(themes)

    return themes, df