# qa_v2.py
import re, faiss, threading

# sentence_transformers takes ~15s to import and load, so it is not loaded at import time.
# Call warm_up() at app start to load it in a background thread; if a question arrives
# before it finishes, model.encode() simply waits for the load to complete.
_model = None
_lock = threading.Lock()
_warming = False

def _load():
    global _model
    with _lock:
        if _model is None:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model

def warm_up():
    """Start loading the model in the background. Safe to call on every Streamlit rerun."""
    global _warming
    if _model is None and not _warming:
        _warming = True
        threading.Thread(target=_load, daemon=True).start()

class _LazyModel:
    def encode(self, *args, **kwargs):
        return _load().encode(*args, **kwargs)

model = _LazyModel()
HEADING_RE=re.compile(r'^(?:(?:ARTICLE|SECTION|CLAUSE|PART|SCHEDULE|ANNEXURE|APPENDIX|EXHIBIT)\s+[A-Z0-9IVXLC]+|\d+[\.)]?\s+.+)',re.I)
def parse_blocks(text):
 text=text.replace("\r","");lines=text.split("\n");blocks=[];cur=[];mode=None
 def flush():
  nonlocal cur,mode
  if cur: blocks.append({"type":mode,"text":"\n".join(cur).strip()})
  cur=[];mode=None
 i=0
 while i<len(lines):
  line=lines[i].rstrip()
  if not line.strip():
   if mode=="paragraph": cur.append("")
   i+=1;continue
  if HEADING_RE.match(line):
   flush();mode="section";cur=[line];i+=1
   while i<len(lines) and not HEADING_RE.match(lines[i].rstrip()):
    cur.append(lines[i].rstrip());i+=1
   flush();continue
  if mode!="paragraph": flush();mode="paragraph";cur=[]
  cur.append(line);i+=1
 flush();return blocks

def build_index(blocks):
 emb=model.encode([b["text"] for b in blocks],convert_to_numpy=True,normalize_embeddings=True).astype("float32")
 idx=faiss.IndexFlatIP(emb.shape[1]);idx.add(emb);return idx

def format_block(block, score, rank):
    """
    Formats one retrieved block.
    """

    block_type = (
        "📄 Contract Section"
        if block["type"] == "section"
        else "📝 Paragraph"
    )

    text = block["text"]

    # Highlight legal numbering
    text = re.sub(
        r'(?m)^(\d+(?:\.\d+)*.*)$',
        r'**\1**',
        text
    )

    # Preserve spacing
    text = text.replace("\n", "\n\n")

    return f"""
## 🏆 Rank {rank}

**Type:** {block_type}

**Similarity Score:** `{score:.3f}`

---

{text}

---

"""

def simple_qa(text, question, top_k=3):

    blocks = parse_blocks(text)

    if not blocks:
        return "Answer not found."

    index = build_index(blocks)

    query = model.encode(
        [question],
        convert_to_numpy=True,
        normalize_embeddings=True
    ).astype("float32")

    scores, ids = index.search(
        query,
        min(top_k, len(blocks))
    )

    # Confidence threshold
    if scores[0][0] < 0.35:
        return "Answer not found."

    output = []

    output.append("# 🔍 Top Matching Results\n")

    for rank, (idx, score) in enumerate(
        zip(ids[0], scores[0]),
        start=1
    ):

        output.append(
            format_block(
                blocks[idx],
                score,
                rank
            )
        )

    return "\n".join(output)