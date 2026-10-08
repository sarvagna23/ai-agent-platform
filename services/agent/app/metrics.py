"""Prometheus metrics for the agent service."""
from prometheus_client import Counter, Histogram

REQUESTS = Counter(
    "agent_requests_total",
    "Requests to /run by outcome",
    ["status"],  # ok, kb_not_ready, llm_unavailable, error
)

REQUEST_SECONDS = Histogram(
    "agent_request_seconds",
    "End to end agent workflow latency in seconds",
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8, 16, 32, 64),
)

RETRIEVAL_SECONDS = Histogram(
    "agent_retrieval_seconds",
    "Embedding plus pgvector search latency in seconds",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)

LLM_SECONDS = Histogram(
    "agent_llm_seconds",
    "LLM call latency in seconds",
    buckets=(0.1, 0.25, 0.5, 1, 2, 4, 8, 16, 32),
)

LLM_TOKENS = Counter(
    "agent_llm_tokens_total",
    "Tokens used by LLM calls",
    ["direction"],  # input or output
)

LLM_ERRORS = Counter(
    "agent_llm_errors_total",
    "Failed LLM calls",
)
