from functools import lru_cache
from config import settings
from fastembed import TextEmbedding
from config.settings import settings

@lru_cache
def get_embedder() -> TextEmbedding:
    return TextEmbedding(model_name=settings.embedding_model)

def embed_documents(texts: list[str]) -> list[list[float]]:
    return [v.tolist() for v in get_embedder().embed(texts)]

def embed_query(text: str) -> list[float]:
    return next(get_embedder().query_embed(text)).tolist()
