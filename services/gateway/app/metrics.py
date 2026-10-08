"""Prometheus metrics for the gateway.

Labels use the route template (for example /ask), never the raw URL,
so the number of time series stays small.
"""
from prometheus_client import Counter, Histogram

REQUESTS = Counter(
    "gateway_requests_total",
    "HTTP requests handled by the gateway",
    ["route", "status"],
)

REQUEST_SECONDS = Histogram(
    "gateway_request_seconds",
    "Gateway request latency in seconds",
    ["route"],
    # LLM-backed requests take seconds, so the buckets reach well past one second.
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8, 16, 32, 64),
)

UPSTREAM_ERRORS = Counter(
    "gateway_upstream_errors_total",
    "Failed calls from the gateway to the agent service",
    ["kind"],
)
