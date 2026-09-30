from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    groq_model: str = "openai/gpt-oss-120b"
    qdrant_url: str
    qdrant_api_key: str
    qdrant_collection: str = "tech_docs"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    data_dir: str = "./DATA"
    rerank_model: str = "ms-marco-MiniLM-L-12-v2"
    retrieve_top_k: int = 20
    rerank_top_n: int = 5
    rerank_threshold: float = 0.3
    max_retrieval_attempts: int = 2
    groq_api_key: str = ""
    portkey_api_key: str
    portkey_config_id: str


settings = Settings()



