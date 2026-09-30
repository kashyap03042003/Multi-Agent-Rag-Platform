from config.settings import settings
from langchain_groq import ChatGroq
from qdrant_client import QdrantClient

llm = ChatGroq(model=settings.groq_model, api_key=settings.groq_api_key)
print("Groq:", llm.invoke("Reply with just: OK").content)

qdrant = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
print("Qdrant collections:", qdrant.get_collections())
