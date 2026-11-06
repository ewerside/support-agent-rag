"""Embed text locally with fastembed and search the help center chunks in Postgres."""

from collections.abc import Iterable
from functools import lru_cache

import psycopg
from fastembed import TextEmbedding
from psycopg.rows import dict_row

import config

EMBED_MODEL = "BAAI/bge-small-en-v1.5"
CACHE_DIR = config.ROOT / ".fastembed_cache"
# The bge model card recommends this instruction for short queries. fastembed's query_embed
# does not add it for this model, so we do.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@lru_cache(maxsize=1)
def _model() -> TextEmbedding:
    # Loading the ONNX model takes a moment, so do it once per process.
    return TextEmbedding(model_name=EMBED_MODEL, cache_dir=str(CACHE_DIR))


def to_pgvector(values: Iterable[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in values) + "]"


def embed_passages(texts: list[str]) -> list[str]:
    """Embed help center chunks, returned as pgvector literals."""
    return [to_pgvector(v) for v in _model().passage_embed(texts)]


def embed_query(query: str) -> str:
    return to_pgvector(next(iter(_model().query_embed(QUERY_PREFIX + query))))


def search(query: str, k: int = 5) -> list[dict]:
    """Return the k chunks closest to the query, best first."""
    with psycopg.connect(
        config.DATABASE_URL, connect_timeout=10, row_factory=dict_row
    ) as conn:
        return conn.execute(
            "select id, article_id, title, content, similarity "
            "from support_agent.match_chunks(%s::vector, %s)",
            (embed_query(query), k),
        ).fetchall()
