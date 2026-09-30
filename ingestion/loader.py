from pathlib import Path
from bs4 import BeautifulSoup
from docx import Document
from pptx import Presentation
from pypdf import PdfReader

SKIP_DIRS = {"processed"}


def read_pdf(path: Path) -> list[tuple]:
    return [(i, p.extract_text() or "") for i, p in enumerate(PdfReader(path).pages, start=1)]


def read_docx(path: Path) -> list[tuple]:
    doc = Document(path)
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text for cell in row.cells))
    return [(None, "\n".join(parts))]


def read_pptx(path: Path) -> list[tuple]:
    slides = []
    for i, slide in enumerate(Presentation(path).slides, start=1):
        texts = [shape.text_frame.text for shape in slide.shapes if shape.has_text_frame]
        slides.append((i, "\n".join(texts)))
    return slides


def read_html(path: Path) -> list[tuple]:
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "html.parser")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    return [(None, soup.get_text(separator="\n"))]


def read_txt(path: Path) -> list[tuple]:
    return [(None, path.read_text(encoding="utf-8", errors="ignore"))]


READERS = {
    ".pdf": read_pdf, ".docx": read_docx, ".pptx": read_pptx,
    ".html": read_html, ".htm": read_html, ".txt": read_txt,
}


def load_documents(data_dir: str) -> list[dict]:
    root = Path(data_dir)
    pages = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        reader = READERS.get(path.suffix.lower())
        if reader is None or SKIP_DIRS & set(rel.parts):
            continue
        try:
            sections = reader(path)
        except Exception as e:
            print(f"Skipped {rel}: {e}")
            continue
        for page, text in sections:
            if text.strip():
                pages.append({
                    "text": text,
                    "source": str(rel),
                    "category": rel.parts[0],
                    "format": path.suffix.lower().lstrip("."),
                    "page": page,
                })
        print(f"Loaded {rel} ({len(sections)} sections)")
    return pages


