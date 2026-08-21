"""
Turn an uploaded file into plain text, whatever format it came in as.
"""
import csv
from pathlib import Path

from pypdf import PdfReader
from docx import Document as DocxDocument


def load_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in (".txt", ".md"):
        return _load_plain(path)
    if suffix == ".pdf":
        return _load_pdf(path)
    if suffix == ".docx":
        return _load_docx(path)
    if suffix == ".csv":
        return _load_csv(path)
    raise ValueError(f"Unsupported file type: {suffix}")


def _load_plain(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _load_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = []
    for i, page in enumerate(reader.pages):
        page_text = page.extract_text() or ""
        if page_text.strip():
            pages.append(f"[page {i + 1}]\n{page_text}")
    return "\n\n".join(pages)


def _load_docx(path: Path) -> str:
    doc = DocxDocument(str(path))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)


def _load_csv(path: Path) -> str:
    """
    Turn each row into a short readable sentence ('col: value, col: value') so it
    embeds and retrieves meaningfully, rather than dumping raw comma-separated
    values (which embed poorly - a vector model doesn't parse tabular structure).
    """
    with path.open(newline="", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        rows = []
        for i, row in enumerate(reader):
            line = ", ".join(f"{k}: {v}" for k, v in row.items() if k)
            rows.append(f"Row {i + 1} - {line}")
    return "\n".join(rows)
