import logging
from contextlib import asynccontextmanager
import uuid
from fastapi import FastAPI, HTTPException, Request
from langchain_core.messages import AIMessage, HumanMessage
from api.schemas import ChatRequest, ChatResponse, Source
from config.settings import settings
from rag.graph import graph
from rag.memory import get_pool
from services import rate_limit
from services.cache_service import get_cache, lookup, store
from services.embeddings import get_embedder
from services.guardrails_service import get_rails, check_input, check_output
from services.rerank_service import get_ranker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_embedder()
    get_ranker()
    get_rails()
    if settings.redis_url:
        get_cache()
    yield
    if settings.database_url:
        get_pool().close()



app = FastAPI(title="Agentic RAG API", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request):
    # Must stay outside the try below, or the 429 would be swallowed into a 500.
    client_id = request.client.host if request.client else "unknown"
    if not rate_limit.allow(client_id):
        logger.warning("Rate limit exceeded for %s", client_id)
        raise HTTPException(status_code=429, detail="Too many requests. Try again in a minute.",
                            headers={"Retry-After": "60"})
    trace_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": req.thread_id, "trace_id": trace_id}}
    try:
        refusal = check_input(req.message)
        if refusal:
            logger.warning("Input blocked for thread %s", req.thread_id)
            return ChatResponse(answer=refusal, search_query="", sources=[], blocked=True, trace_id=trace_id)

        is_new_thread = not graph.get_state(config).values.get("messages")
        if is_new_thread:
            hit = lookup(req.message)
            if hit:
                graph.update_state(
                    config,
                    {"messages": [HumanMessage(req.message), AIMessage(hit["answer"])]},
                    as_node="responder",
                )
                return ChatResponse(
                    answer=hit["answer"],
                    search_query=hit["search_query"],
                    sources=[Source(**s) for s in hit["sources"]],
                    cached=True,
                    trace_id=trace_id,
                )

        result = graph.invoke({"messages": [HumanMessage(req.message)]}, config)
        last = result["messages"][-1]

        refusal = check_output(req.message, last.content)
        if refusal:
            logger.warning("Output blocked for thread %s", req.thread_id)
            graph.update_state(config, {"messages": [AIMessage(content=refusal, id=last.id)]})
            return ChatResponse(answer=refusal, search_query="", sources=[], blocked=True, trace_id=trace_id)
    except Exception:
        logger.exception("Chat failed for thread %s", req.thread_id)
        raise HTTPException(status_code=500, detail="Failed to generate an answer.")

    sources = [
        Source(source=d["source"], page=d["page"], score=d["rerank_score"])
        for d in result["documents"]
    ]
    if is_new_thread and result["needs_retrieval"] and sources:
        store(req.message, last.content, result["search_query"], [s.model_dump() for s in sources])
    return ChatResponse(
        answer=last.content, search_query=result["search_query"], sources=sources, trace_id=trace_id
    )
