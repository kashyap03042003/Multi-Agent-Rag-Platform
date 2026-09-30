from functools import lru_cache
from flashrank import Ranker, RerankRequest
from config.settings import settings

@lru_cache
def get_ranker() -> Ranker:
    return Ranker(model_name=settings.rerank_model, cache_dir=".cache/flashrank")

def rerank(query: str, docs: list[dict]) -> list[dict]:
    if not docs:
        return []
    passages = [{"id": i, "text": d["text"]} for i, d in enumerate(docs)]
    results = get_ranker().rerank(RerankRequest(query=query, passages=passages))
    ranked = [{**docs[r["id"]], "rerank_score": float(r["score"])} for r in results]
    kept = [d for d in ranked if d["rerank_score"] >= settings.rerank_threshold]
    return kept[: settings.rerank_top_n]
