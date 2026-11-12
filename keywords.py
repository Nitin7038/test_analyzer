def extract_keywords(text):
    # imported here: scikit-learn takes ~3s to import and would otherwise slow app startup
    from sklearn.feature_extraction.text import TfidfVectorizer
    vectorizer = TfidfVectorizer(stop_words="english", max_features=10)
    X = vectorizer.fit_transform([text])
    return vectorizer.get_feature_names_out()