from langchain_openai import ChatOpenAI
from portkey_ai import PORTKEY_GATEWAY_URL, createHeaders
from config.settings import settings

def get_llm(trace_id: str = "system", user: str = "system") -> ChatOpenAI:
    headers = createHeaders(
        api_key=settings.portkey_api_key,
        config=settings.portkey_config_id,
        trace_id=trace_id,
        metadata={"_user": user, "app": "agentic-rag"},
    )
    return ChatOpenAI(
        model=settings.groq_model,
        api_key="portkey",
        base_url=PORTKEY_GATEWAY_URL,
        default_headers=headers,
        temperature=0,
    )
