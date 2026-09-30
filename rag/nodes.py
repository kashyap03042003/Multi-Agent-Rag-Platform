from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage
from config.settings import settings
from rag.state import AgentState
from services.llm import get_llm
from services.embeddings import embed_query
from services.qdrant_service import search
from services.rerank_service import rerank
import logging
from openai import BadRequestError
from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)


class Plan(BaseModel):
    needs_retrieval: bool = Field(description="True if answering requires the technical knowledge base")
    search_query: str = Field(description="Standalone search query rewritten from the conversation; empty if no retrieval")


PLANNER_PROMPT = """You are the planner for a technical assistant whose knowledge base contains
technical documentation (Kubernetes, batch jobs and scheduling, autoscaling, data platform job tooling, and related infrastructure).
Given the conversation, decide whether the latest user message needs the knowledge base.
- ONLY greetings, thanks, or questions about what the assistant can do: needs_retrieval = false.
- ANY technical or factual question, even if you are unsure the knowledge base covers it: needs_retrieval = true,
  and rewrite the latest message into a standalone search query, resolving references like "it" or "that"
  using earlier turns. Never answer from your own knowledge; when in doubt, retrieve."""

REFINE_PROMPT = """The search query below found no relevant results in a technical documentation knowledge base.
Rewrite it using different keywords or more specific technical terms. Return only the new query.

Query: {query}"""

RESPONDER_PROMPT = """You are a helpful technical assistant.
Answer using ONLY the context below. If the context does not contain the answer, say you don't know.
Cite sources as [source, page] after the sentences they support.

Context:
{context}"""

def llm_for(config: RunnableConfig):
    c = config.get("configurable", {})
    return get_llm(trace_id=c.get("trace_id", "system"), user=c.get("thread_id", "system"))


def planner(state: AgentState, config: RunnableConfig) -> dict:
    llm = llm_for(config).with_structured_output(Plan, method="function_calling")
    try:
        plan = llm.invoke([SystemMessage(PLANNER_PROMPT), *state["messages"]])
    except BadRequestError:
        logger.warning("Planner returned no structured output; skipping retrieval")
        plan = Plan(needs_retrieval=False, search_query="")
    return {
        "needs_retrieval": plan.needs_retrieval,
        "search_query": plan.search_query,
        "documents": [],
        "attempts": 0,
    }


def retriever(state: AgentState) -> dict:
    hits = search(embed_query(state["search_query"]), limit=settings.retrieve_top_k)
    docs = rerank(state["search_query"], hits)
    return {"documents": docs, "attempts": state["attempts"] + 1}


def refine_query(state: AgentState, config: RunnableConfig) -> dict:
    prompt = REFINE_PROMPT.format(query=state["search_query"])
    return {"search_query": llm_for(config).invoke(prompt).content.strip()}


def format_context(docs: list[dict]) -> str:
    return "\n\n".join(f"[{d['source']}, page {d['page']}]\n{d['text']}" for d in docs)
    

def responder(state: AgentState, config: RunnableConfig) -> dict:
    if state["needs_retrieval"]:
        context = format_context(state["documents"]) or "No relevant documents found."
        system = RESPONDER_PROMPT.format(context=context)
    else:
        system = (
            "You are a documentation assistant. Reply briefly and naturally to greetings, thanks, "
            "or questions about what you can do. Do not answer technical or factual questions from "
            "your own knowledge; say you can only answer from the documentation."
        )
    answer = llm_for(config).invoke([SystemMessage(system), *state["messages"]])
    return {"messages": [answer]}


