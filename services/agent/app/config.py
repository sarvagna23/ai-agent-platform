"""Agent settings, all read from environment variables."""
import os

# --- Database (pgvector) ---
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/agent")

# --- Embeddings ---
# bge-small produces 384 dimensional vectors. Change both together if you swap the model.
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
EMBEDDING_DIM = 384
# The Docker image bakes the model into this folder so pods start without downloading it.
EMBEDDING_CACHE_DIR = os.environ.get("EMBEDDING_CACHE_DIR", "/opt/fastembed")
PRELOAD_EMBEDDER = os.environ.get("PRELOAD_EMBEDDER", "true").lower() == "true"

# --- Retrieval ---
TOP_K = int(os.environ.get("TOP_K", "4"))

# --- LLM ---
# "anthropic" calls Claude. "echo" skips the LLM and returns the retrieved sources,
# which is useful for load tests that should not spend tokens.
LLM_MODE = os.environ.get("LLM_MODE", "anthropic")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
MAX_OUTPUT_TOKENS = int(os.environ.get("MAX_OUTPUT_TOKENS", "400"))
