import logging
import socket
from pathlib import Path
from config.settings import settings
from ingestion.chunker import chunk_pages
from ingestion.events import DLQ, GROUP, STREAM, ensure_group, get_redis
from ingestion.loader import load_file
from services.cache_service import clear as clear_cache
from services.embeddings import embed_documents, get_embedder
from services.qdrant_service import chunk_id, delete_stale, ensure_collection, ensure_source_index, upsert_chunks

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("worker")

CONSUMER = socket.gethostname()
BATCH_SIZE = 64
MAX_DELIVERIES = 3
CLAIM_IDLE_MS = 60_000


def process(event: dict) -> int:
    root = Path(settings.data_dir)
    source = event["path"]
    chunks = []
    # Reconcile with the file's current state: atomic saves emit upsert+delete in either order.
    if (root / source).exists():
        chunks = chunk_pages(load_file(root / source, root))
        for start in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[start:start + BATCH_SIZE]
            upsert_chunks(batch, embed_documents([c["text"] for c in batch]))
    delete_stale(source, [chunk_id(c) for c in chunks])
    clear_cache()
    return len(chunks)


def times_delivered(r, msg_id: str) -> int:
    info = r.xpending_range(STREAM, GROUP, min=msg_id, max=msg_id, count=1)
    return info[0]["times_delivered"] if info else 1


def handle(r, msg_id: str, event: dict) -> None:
    try:
        n = process(event)
        r.xack(STREAM, GROUP, msg_id)
        logger.info("%s %s -> %d chunks", event["action"], event["path"], n)
    except Exception as e:
        attempts = times_delivered(r, msg_id)
        logger.exception("Failed %s (attempt %d/%d)", event["path"], attempts, MAX_DELIVERIES)
        if attempts >= MAX_DELIVERIES:
            r.xadd(DLQ, {**event, "error": f"{type(e).__name__}: {e}"[:500], "msg_id": msg_id})
            r.xack(STREAM, GROUP, msg_id)
            logger.error("Moved %s to dead-letter queue", event["path"])


def next_messages(r) -> list:
    _, reclaimed, *_ = r.xautoclaim(STREAM, GROUP, CONSUMER, min_idle_time=CLAIM_IDLE_MS, start_id="0-0", count=1)
    if reclaimed:
        return reclaimed
    response = r.xreadgroup(GROUP, CONSUMER, {STREAM: ">"}, count=1, block=5000)
    return [msg for _, msgs in response for msg in msgs] if response else []


def main():
    r = get_redis()
    ensure_group(r)
    ensure_collection()
    ensure_source_index()
    get_embedder()
    logger.info("Worker %s listening on %s", CONSUMER, STREAM)
    while True:
        for msg_id, event in next_messages(r):
            handle(r, msg_id, event)


if __name__ == "__main__":
    main()
