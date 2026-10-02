from langgraph.graph import StateGraph, START, END
from config.settings import settings
from rag.memory import get_checkpointer
from rag.state import AgentState
from rag.nodes import planner, retriever, refine_query, responder


def route_after_planner(state: AgentState) -> str:
    return "retriever" if state["needs_retrieval"] else "responder"


def route_after_retriever(state: AgentState) -> str:
    if state["documents"] or state["attempts"] >= settings.max_retrieval_attempts:
        return "responder"
    return "refine_query"


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("planner", planner)
    g.add_node("retriever", retriever)
    g.add_node("refine_query", refine_query)
    g.add_node("responder", responder)

    g.add_edge(START, "planner")
    g.add_conditional_edges("planner", route_after_planner, ["retriever", "responder"])
    g.add_conditional_edges("retriever", route_after_retriever, ["refine_query", "responder"])
    g.add_edge("refine_query", "retriever")
    g.add_edge("responder", END)

    return g.compile(checkpointer=get_checkpointer())


graph = build_graph()
