import logging
from contextlib import asynccontextmanager
import uuid
from fastapi import FastAPI, HTTPException
from langchain_core.messages import HumanMessage
from api.schemas import ChatRequest, ChatResponse, Source
from rag.graph import graph
from services.embeddings import get_embedder
from services.rerank_service import get_ranker
from langchain_core.messages import AIMessage, HumanMessage
from services.guardrails_service import get_rails, check_input, check_output


logger = logging.getLogger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_embedder()
    get_ranker()
    get_rails()
    yield


app = FastAPI(title="Agentic RAG API", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    trace_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": req.thread_id, "trace_id": trace_id}}
    try:
        refusal = check_input(req.message)
        if refusal:
            logger.warning("Input blocked for thread %s", req.thread_id)
            return ChatResponse(answer=refusal, search_query="", sources=[], blocked=True)

        result = graph.invoke({"messages": [HumanMessage(req.message)]}, config)
        last = result["messages"][-1]

        refusal = check_output(req.message, last.content)
        if refusal:
            logger.warning("Output blocked for thread %s", req.thread_id)
            graph.update_state(config, {"messages": [AIMessage(content=refusal, id=last.id)]})
            return ChatResponse(answer=refusal, search_query="", sources=[], blocked=True)
    except Exception:
        logger.exception("Chat failed for thread %s", req.thread_id)
        raise HTTPException(status_code=500, detail="Failed to generate an answer.")

    sources = [
        Source(source=d["source"], page=d["page"], score=d["rerank_score"])
        for d in result["documents"]
    ]
    return ChatResponse(answer=last.content, search_query=result["search_query"], sources=sources)
