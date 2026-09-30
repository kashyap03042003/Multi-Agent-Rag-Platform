from typing import Annotated, TypedDict
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    search_query: str
    needs_retrieval: bool
    documents: list[dict]
    attempts: int



