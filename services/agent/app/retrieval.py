"""Embedding and vector search over pgvector.

Heavy libraries (fastembed, psycopg) are imported inside the functions that need them,
so unit tests can import this module without installing them.
"""
from functools import lru_cache

from app import config


class KnowledgeBaseNotReady(Exception):
    """The database is unreachable or the documents table has not been created yet."""


@lru_cache(maxsize=1)
def get_embedder():
    """Load the embedding model once per process."""
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=config.EMBEDDING_MODEL, cache_dir=config.EMBEDDING_CACHE_DIR)


def embed_text(text: str) -> list[float]:
    """Turn text into a vector (a list of floats)."""
    embedder = get_embedder()
    vectors = list(embedder.embed([text]))
    return vectors[0].tolist()


def to_vector_literal(vector: list[float]) -> str:
    """Format a vector the way pgvector accepts it in SQL, for example '[0.1,0.2,0.3]'."""
    numbers = ",".join(f"{value:.6f}" for value in vector)
    return f"[{numbers}]"


_pool = None


def get_pool():
    """Create the connection pool on first use."""
    global _pool
    if _pool is None:
        from psycopg_pool import ConnectionPool

        _pool = ConnectionPool(config.DATABASE_URL, min_size=1, max_size=5, open=False)
        _pool.open()
    return _pool


def _is_not_ready_error(error: Exception) -> bool:
    """True for the errors that mean 'database not up or not loaded yet'."""
    from psycopg import OperationalError, errors
    from psycopg_pool import PoolTimeout

    return isinstance(error, (errors.UndefinedTable, OperationalError, PoolTimeout))


SEARCH_SQL = """
SELECT title, content, embedding <=> %s::vector AS distance
FROM documents
ORDER BY embedding <=> %s::vector
LIMIT %s
"""


def search(query: str, top_k: int) -> list[dict]:
    """Return the top_k documents closest to the query (smaller distance is closer)."""
    vector_literal = to_vector_literal(embed_text(query))
    try:
        with get_pool().connection(timeout=5) as connection:
            rows = connection.execute(SEARCH_SQL, (vector_literal, vector_literal, top_k)).fetchall()
    except Exception as error:
        if _is_not_ready_error(error):
            raise KnowledgeBaseNotReady(str(error)) from error
        raise
    return [{"title": title, "content": content, "distance": float(distance)} for title, content, distance in rows]
