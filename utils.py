import re
import pdfplumber
import docx
import pytesseract
from PIL import Image

def clean_text(text):
    # Normalize Windows line endings
    text = text.replace("\r", "")

    # Remove extra spaces and tabs only
    text = re.sub(r"[ \t]+", " ", text)

    # Remove excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()

def extract_text_from_pdf(file):
    text = ""

    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:

            page_text = page.extract_text(
                x_tolerance=2,
                y_tolerance=2
            )

            if page_text:
                text += page_text
                text += "\n\n"

    return text

def extract_text_from_docx(file):
    doc = docx.Document(file)
    return "\n".join([para.text for para in doc.paragraphs])

def ocr_image(file):
    image = Image.open(file)
    return pytesseract.image_to_string(image)