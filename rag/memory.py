from functools import lru_cache
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from config.settings import settings


@lru_cache
def get_pool() -> ConnectionPool:
    return ConnectionPool(
        conninfo=settings.database_url,
        max_size=10,
        open=True,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )


def get_checkpointer():
    if not settings.database_url:
        return MemorySaver()
    saver = PostgresSaver(get_pool())
    saver.setup()
    return saver
