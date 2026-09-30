from functools import lru_cache
from pathlib import Path
from nemoguardrails import LLMRails, RailsConfig
from services.llm import get_llm

CONFIG_PATH = Path(__file__).resolve().parent.parent / "guardrails" / "config"


@lru_cache
def get_rails() -> LLMRails:
    return LLMRails(RailsConfig.from_path(str(CONFIG_PATH)), llm=get_llm())


def check_input(message: str) -> str | None:
    result = get_rails().generate(
        messages=[{"role": "user", "content": message}],
        options={"rails": ["input"]},
    )
    reply = result.response[-1]["content"]
    return None if reply == message else reply


def check_output(message: str, answer: str) -> str | None:
    result = get_rails().generate(
        messages=[
            {"role": "user", "content": message},
            {"role": "assistant", "content": answer},
        ],
        options={"rails": ["output"]},
    )
    reply = result.response[-1]["content"]
    return None if reply == answer else reply
