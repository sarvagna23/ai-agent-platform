"""Gateway service: the public entry point. It validates the request, forwards it to
the agent service, and records request metrics for Prometheus.

Run locally:  uvicorn app.main:app --port 8000
"""
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field

from app import config, metrics

# One shared HTTP client for the whole process (created at startup, closed at shutdown).
_http_client: httpx.AsyncClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _http_client
    _http_client = httpx.AsyncClient(timeout=config.AGENT_TIMEOUT_SECONDS)
    yield
    await _http_client.aclose()


app = FastAPI(title="AI Platform Gateway", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


class Source(BaseModel):
    title: str
    distance: float


class AskResponse(BaseModel):
    answer: str
    sources: list[Source]
    timings_ms: dict[str, int]


@app.middleware("http")
async def record_request_metrics(request: Request, call_next):
    """Time every request and count it by route and status code."""
    started_at = time.perf_counter()
    status_code = 500  # stays 500 if the handler raises before a response exists
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        elapsed_seconds = time.perf_counter() - started_at
        route = request.scope.get("route")
        route_label = route.path if route else "unmatched"
        if route_label != "/metrics":  # do not count Prometheus scrapes as traffic
            metrics.REQUESTS.labels(route=route_label, status=str(status_code)).inc()
            metrics.REQUEST_SECONDS.labels(route=route_label).observe(elapsed_seconds)


async def call_agent(question: str) -> dict:
    """Send the question to the agent service and return its JSON answer."""
    assert _http_client is not None, "HTTP client is created at startup"
    response = await _http_client.post(f"{config.AGENT_URL}/run", json={"question": question})
    response.raise_for_status()
    return response.json()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/metrics", include_in_schema=False)
def metrics_endpoint() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest) -> dict:
    """Forward the question to the agent. Any agent failure becomes a 502 for the client."""
    try:
        return await call_agent(request.question)
    except httpx.HTTPStatusError as error:
        metrics.UPSTREAM_ERRORS.labels(kind="status").inc()
        raise HTTPException(status_code=502, detail=f"agent returned {error.response.status_code}")
    except httpx.HTTPError:
        metrics.UPSTREAM_ERRORS.labels(kind="connection").inc()
        raise HTTPException(status_code=502, detail="agent is unreachable")
# timing test
