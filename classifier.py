import re

def classify_document(text):

    text_lower = text.lower()

    categories = {
        "AI / Machine Learning": [
            "neural network", "deep learning", "machine learning",
            "artificial intelligence", "cnn", "rnn", "transformer",
            "bert", "tensorflow", "pytorch", "nlp",
            "computer vision", "classification", "regression"
        ],

        "Legal Document": [
            "agreement", "contract", "hereby", "plaintiff",
            "defendant", "court", "law", "legal",
            "jurisdiction", "terms and conditions"
        ],

        "Job Description": [
            "responsibilities", "requirements", "job role",
            "experience", "skills required", "qualification",
            "salary", "apply now", "job description"
        ],

        "Research Paper": [
            "abstract", "methodology", "references",
            "literature review", "results", "conclusion",
            "research", "experiment"
        ],

        "Syllabus": [
            "unit 1", "unit 2", "course outcomes",
            "syllabus", "credits", "module",
            "semester", "curriculum"
        ],

        "Resume / CV": [
            "education", "projects", "skills",
            "internship", "experience", "certifications",
            "resume", "curriculum vitae"
        ],

        "Financial Document": [
            "invoice", "balance sheet", "revenue",
            "profit", "tax", "financial statement",
            "gst", "payment"
        ],

        "Medical Document": [
            "patient", "diagnosis", "treatment",
            "prescription", "hospital", "medical",
            "symptoms", "disease"
        ]
    }

    scores = {}

    for category, keywords in categories.items():

        score = 0

        for keyword in keywords:
            matches = len(re.findall(r'\b' + re.escape(keyword) + r'\b', text_lower))
            score += matches

        scores[category] = score

    best_category = max(scores, key=scores.get)

    if scores[best_category] == 0:
        return "General Document", scores

    return best_category, scores