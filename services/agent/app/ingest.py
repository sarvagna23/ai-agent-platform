"""Load the knowledge base into pgvector. Safe to run repeatedly.

Run locally:   python -m app.ingest
In the cluster it runs as an Argo CD PostSync Job, after every sync.
"""
import json
from pathlib import Path

from app import config, retrieval

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "knowledge.jsonl"

CREATE_STATEMENTS = [
    "CREATE EXTENSION IF NOT EXISTS vector",
    f"""
    CREATE TABLE IF NOT EXISTS documents (
        id SERIAL PRIMARY KEY,
        title TEXT UNIQUE NOT NULL,
        content TEXT NOT NULL,
        embedding VECTOR({config.EMBEDDING_DIM}) NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS documents_embedding_idx ON documents USING hnsw (embedding vector_cosine_ops)",
]

UPSERT_SQL = """
INSERT INTO documents (title, content, embedding)
VALUES (%s, %s, %s::vector)
ON CONFLICT (title) DO UPDATE SET content = EXCLUDED.content, embedding = EXCLUDED.embedding
"""


def load_entries(path: Path) -> list[dict]:
    """Read one JSON object per line: {"title": ..., "content": ...}."""
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main() -> None:
    import psycopg

    entries = load_entries(DATA_FILE)
    texts = [f"{entry['title']}. {entry['content']}" for entry in entries]
    print(f"Embedding {len(texts)} documents with {config.EMBEDDING_MODEL}")
    vectors = list(retrieval.get_embedder().embed(texts))

    # The connection context manager commits when the block ends without an error.
    with psycopg.connect(config.DATABASE_URL) as connection:
        for statement in CREATE_STATEMENTS:
            connection.execute(statement)
        for entry, vector in zip(entries, vectors):
            vector_literal = retrieval.to_vector_literal(vector.tolist())
            connection.execute(UPSERT_SQL, (entry["title"], entry["content"], vector_literal))

    print(f"Loaded {len(entries)} documents into pgvector")


if __name__ == "__main__":
    main()
