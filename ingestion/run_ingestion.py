from config.settings import settings
from ingestion.loader import load_documents
from ingestion.chunker import chunk_pages
from services.embeddings import embed_documents
from services.qdrant_service import ensure_collection, upsert_chunks, get_client

BATCH_SIZE = 64

def main():
    pages = load_documents(settings.data_dir)
    chunks = chunk_pages(pages)
    print(f"{len(pages)} pages -> {len(chunks)} chunks")

    ensure_collection()
    for start in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[start:start + BATCH_SIZE]
        vectors = embed_documents([c["text"] for c in batch])
        upsert_chunks(batch, vectors)
        print(f"Upserted {start + len(batch)}/{len(chunks)}")

    count = get_client().count(settings.qdrant_collection).count
    print(f"Collection '{settings.qdrant_collection}' now has {count} points")

if __name__ == "__main__":
    main()
