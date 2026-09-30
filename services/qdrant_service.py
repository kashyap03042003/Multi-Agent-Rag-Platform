import uuid
from functools import lru_cache
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from config.settings import settings

@lru_cache
def get_client() -> QdrantClient:
    return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key, timeout=60)

def ensure_collection() -> None:
    client = get_client()
    if not client.collection_exists(settings.qdrant_collection):
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(size=settings.embedding_dim, distance=Distance.COSINE),
        )

def chunk_id(chunk: dict) -> str:
    key = f"{chunk['source']}:{chunk['page']}:{chunk['chunk_index']}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))

def upsert_chunks(chunks: list[dict], vectors: list[list[float]]) -> None:
    points = [PointStruct(id=chunk_id(c), vector=v, payload=c) for c, v in zip(chunks, vectors)]
    get_client().upsert(collection_name=settings.qdrant_collection, points=points)


def search(query_vector: list[float], limit: int) -> list[dict]:
    result = get_client().query_points(
        collection_name=settings.qdrant_collection,
        query=query_vector,
        limit=limit,
        with_payload=True,
    )
    return [{**p.payload, "vector_score": p.score} for p in result.points]
