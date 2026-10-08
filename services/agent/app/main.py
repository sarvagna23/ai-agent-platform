"""Agent service: runs the LangGraph workflow and exposes Prometheus metrics.

Run locally:  uvicorn app.main:app --port 8001
"""
import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field

from app import config, llm, metrics, retrieval
from app.graph import build_graph


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the embedding model at startup so the first request is not slow."""
    if config.PRELOAD_EMBEDDER:
        await asyncio.to_thread(retrieval.get_embedder)
    yield


app = FastAPI(title="AI Platform Agent", lifespan=lifespan)

# The real wiring: pgvector search and the Claude call.
graph = build_graph(retrieval.search, llm.generate_answer)


class RunRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


class Source(BaseModel):
    title: str
    distance: float


class RunResponse(BaseModel):
    answer: str
    sources: list[Source]
    timings_ms: dict[str, int]


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/metrics", include_in_schema=False)
def metrics_endpoint() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/run", response_model=RunResponse)
async def run(request: RunRequest) -> dict:
    """Run the workflow once. Counts the outcome and records the total latency."""
    started_at = time.perf_counter()
    status = "ok"
    try:
        final_state = await graph.ainvoke({"question": request.question})
    except retrieval.KnowledgeBaseNotReady:
        status = "kb_not_ready"
        raise HTTPException(status_code=503, detail="knowledge base is not loaded yet")
    except llm.LLMUnavailable as error:
        status = "llm_unavailable"
        raise HTTPException(status_code=503, detail=str(error))
    except Exception:
        status = "error"
        raise
    finally:
        metrics.REQUESTS.labels(status=status).inc()
        metrics.REQUEST_SECONDS.observe(time.perf_counter() - started_at)

    sources = [{"title": item["title"], "distance": item["distance"]} for item in final_state.get("contexts", [])]
    return {
        "answer": final_state["answer"],
        "sources": sources,
        "timings_ms": final_state["timings_ms"],
    }
