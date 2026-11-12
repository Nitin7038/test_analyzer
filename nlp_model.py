# Importing spaCy (which pulls in torch) and loading en_core_web_md takes several seconds,
# so it is not done at import time. Call warm_up() at app start to load it in a background
# thread; get_nlp() returns the model, waiting for the load to finish if it is still running.
# Module globals survive Streamlit reruns, so the model is loaded once per server process.
import threading

_nlp = None
_lock = threading.Lock()
_warming = False


def get_nlp():
    global _nlp
    with _lock:
        if _nlp is None:
            import spacy
            _nlp = spacy.load("en_core_web_md")
    return _nlp


def warm_up():
    """Start loading the model in the background. Safe to call on every Streamlit rerun."""
    global _warming
    if _nlp is None and not _warming:
        _warming = True
        threading.Thread(target=get_nlp, daemon=True).start()
