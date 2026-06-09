# topic_modeling.py

import re
import pandas as pd

from sklearn.feature_extraction.text import CountVectorizer
from sklearn.decomposition import LatentDirichletAllocation


def extract_topics(text, n_topics=3, words_per_topic=6):

    # Clean text
    text = re.sub(r'[^a-zA-Z\s]', ' ', text)
    text = text.lower()

    # Split document into chunks
    chunk_size = 1000

    chunks = [
        text[i:i + chunk_size]
        for i in range(0, len(text), chunk_size)
    ]

    if len(chunks) < n_topics:
        chunks = chunks * n_topics

    vectorizer = CountVectorizer(
        stop_words="english",
        max_features=1000
    )

    X = vectorizer.fit_transform(chunks)

    lda = LatentDirichletAllocation(
        n_components=n_topics,
        random_state=42
    )

    lda.fit(X)

    feature_names = vectorizer.get_feature_names_out()

    topics = []

    for idx, topic in enumerate(lda.components_):

        top_indices = topic.argsort()[-words_per_topic:][::-1]

        keywords = [
            feature_names[i]
            for i in top_indices
        ]

        topic_name = " ".join(keywords[:2]).title()

        topics.append({
            "topic_id": idx + 1,
            "topic_name": topic_name,
            "keywords": keywords
        })

    # Topic distribution
    topic_distribution = lda.transform(X)

    avg_distribution = topic_distribution.mean(axis=0)

    topic_scores = (
        avg_distribution /
        avg_distribution.sum()
    ) * 100

    chart_df = pd.DataFrame({
        "Topic": [
            t["topic_name"]
            for t in topics
        ],
        "Importance": topic_scores
    })

    return topics, chart_df