import json
import logging
from functools import lru_cache
from redisvl.extensions.cache.llm import SemanticCache
from redisvl.utils.vectorize import CustomTextVectorizer
from config.settings import settings
from services.embeddings import embed_query

logger = logging.getLogger(__name__)


@lru_cache
def get_cache() -> SemanticCache:
    return SemanticCache(
        name="rag_answers",
        redis_url=settings.redis_url,
        vectorizer=CustomTextVectorizer(embed=embed_query),
        distance_threshold=settings.cache_distance_threshold,
        ttl=settings.cache_ttl_seconds,
    )


def lookup(question: str) -> dict | None:
    if not settings.redis_url:
        return None
    try:
        hits = get_cache().check(prompt=question, num_results=1)
    except Exception:
        logger.exception("Semantic cache lookup failed; continuing without cache")
        return None
    if not hits:
        return None
    hit = hits[0]
    metadata = hit.get("metadata") or {}
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    logger.info("Cache hit (distance %.3f) for %r ~ %r", float(hit["vector_distance"]), question, hit["prompt"])
    return {"answer": hit["response"], **metadata}


def store(question: str, answer: str, search_query: str, sources: list[dict]) -> None:
    if not settings.redis_url:
        return
    try:
        get_cache().store(
            prompt=question,
            response=answer,
            metadata={"search_query": search_query, "sources": sources},
        )
    except Exception:
        logger.exception("Semantic cache store failed")
