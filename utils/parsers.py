import fitz
from docx import Document

def extract_paragraphs_from_pdf(file):
    text = ""
    with fitz.open(stream=file.read(), filetype="pdf") as doc:
        for page in doc:
            page_text = page.get_text("text")
            text += page_text + "\n"
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    return paragraphs

def extract_paragraphs_from_docx(file):
    doc = Document(file)
    return [para.text.strip() for para in doc.paragraphs if para.text.strip()]
