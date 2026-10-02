from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    thread_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=4000)


class Source(BaseModel):
    source: str
    page: int | None
    score: float


class ChatResponse(BaseModel):
    answer: str
    search_query: str
    sources: list[Source]
    blocked: bool = False
    trace_id: str = ""
    cached: bool = False

