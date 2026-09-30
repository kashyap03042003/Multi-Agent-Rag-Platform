import re
from langchain_text_splitters import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=150)

def clean_text(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def chunk_pages(pages: list[dict], min_chars: int = 50) -> list[dict]:
    chunks = []
    for page in pages:
        for i, piece in enumerate(splitter.split_text(clean_text(page["text"]))):
            if len(piece) >= min_chars:
                chunks.append({**page, "text": piece, "chunk_index": i})
    return chunks

