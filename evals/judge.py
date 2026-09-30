import asyncio
import time
from pydantic import BaseModel
from deepeval.models import DeepEvalBaseLLM
from services.llm import get_llm

MAX_ATTEMPTS = 6
BACKOFF_SECONDS = 20


def is_rate_limited(e: Exception) -> bool:
    return getattr(e, "status_code", None) == 429 or "rate limit" in str(e).lower()


class GatewayJudge(DeepEvalBaseLLM):
    def __init__(self):
        self.model = get_llm(trace_id="evals", user="evals")

    def load_model(self):
        return self.model

    def _runnable(self, schema):
        # DeepEval passes `schema` when it needs JSON; json_mode makes the output parse reliably.
        return self.model if schema is None else self.model.with_structured_output(schema, method="json_mode")

    def generate(self, prompt: str, schema: type[BaseModel] | None = None):
        runnable = self._runnable(schema)
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                result = runnable.invoke(prompt)
                return result if schema else result.content
            except Exception as e:
                if not is_rate_limited(e) or attempt == MAX_ATTEMPTS:
                    raise
                # Groq free tier is 8K tokens/minute; wait for the window to reset.
                time.sleep(BACKOFF_SECONDS * attempt)

    async def a_generate(self, prompt: str, schema: type[BaseModel] | None = None):
        return await asyncio.to_thread(self.generate, prompt, schema)

    def get_model_name(self) -> str:
        return "portkey-gateway-judge"
