from utils import clean_text

def summarize_text(text, nlp, num_sentences=None):
    text = clean_text(text)

    if len(text.split()) < 50:
        return text

    if num_sentences is None:
        num_sentences = max(3, int(len(text.split()) * 0.02))

    doc = nlp(text)

    word_freq = {}
    for token in doc:
        if token.is_stop or token.is_punct:
            continue
        word = token.text.lower()
        word_freq[word] = word_freq.get(word, 0) + 1

    if not word_freq:
        return text

    max_freq = max(word_freq.values())

    for word in word_freq:
        word_freq[word] /= max_freq

    sentence_scores = {}

    for sent in doc.sents:
        for token in sent:
            word = token.text.lower()
            if word in word_freq:
                sentence_scores[sent] = sentence_scores.get(sent, 0) + word_freq[word]

    sorted_sentences = sorted(
        sentence_scores,
        key=sentence_scores.get,
        reverse=True
    )

    top_sentences = sorted(sorted_sentences[:num_sentences], key=lambda s: s.start)

    return " ".join([sent.text for sent in top_sentences])