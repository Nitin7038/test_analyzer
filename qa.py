def simple_qa(text, question):
    sentences = text.split(".")
    for sent in sentences:
        if any(word.lower() in sent.lower() for word in question.split()):
            return sent
    return "Answer not found."




from sentence_transformers import SentenceTransformer, util
import torch
import re

# Load pre-trained model (BERT-based)
model = SentenceTransformer('all-MiniLM-L6-v2')

def preprocess_text(text):
    # Better sentence splitting than "."
    sentences = re.split(r'(?<=[.!?]) +', text)
    return [s.strip() for s in sentences if len(s.strip()) > 0]

def simple_qa_bkp(text, question):
    sentences = preprocess_text(text)

    if not sentences:
        return "No valid content found."

    # Convert sentences into embeddings
    sentence_embeddings = model.encode(sentences, convert_to_tensor=True)

    # Convert question into embedding
    question_embedding = model.encode(question, convert_to_tensor=True)

    # Compute similarity
    similarities = util.cos_sim(question_embedding, sentence_embeddings)[0]

    # Get best match
    best_idx = torch.argmax(similarities).item()
    best_score = similarities[best_idx].item()

    # Confidence threshold (important)
    if best_score < 0.3:
        return "Answer not found."

    return sentences[best_idx]