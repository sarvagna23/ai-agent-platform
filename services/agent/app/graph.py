"""The LangGraph workflow:  retrieve -> generate   (or -> no_context when nothing is found).

The search and generate functions are passed in, so tests can use fakes and the
real wiring happens in main.py.
"""
import asyncio
import time
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app import config, metrics

NO_CONTEXT_ANSWER = "I don't have any information about that in my knowledge base."


class AgentState(TypedDict, total=False):
    question: str
    contexts: list[dict]
    answer: str
    timings_ms: dict


def build_graph(search_fn, generate_fn):
    """Build and compile the workflow around the given search and generate functions."""

    async def retrieve_node(state: AgentState) -> dict:
        """Find the closest documents. Search is blocking, so it runs in a worker thread."""
        started_at = time.perf_counter()
        contexts = await asyncio.to_thread(search_fn, state["question"], config.TOP_K)
        elapsed_seconds = time.perf_counter() - started_at

        metrics.RETRIEVAL_SECONDS.observe(elapsed_seconds)
        timings = dict(state.get("timings_ms", {}))
        timings["retrieval"] = round(elapsed_seconds * 1000)
        return {"contexts": contexts, "timings_ms": timings}

    async def generate_node(state: AgentState) -> dict:
        """Ask the LLM for an answer grounded in the retrieved documents."""
        started_at = time.perf_counter()
        try:
            result = await generate_fn(state["question"], state["contexts"])
        except Exception:
            metrics.LLM_ERRORS.inc()
            raise
        elapsed_seconds = time.perf_counter() - started_at

        metrics.LLM_SECONDS.observe(elapsed_seconds)
        metrics.LLM_TOKENS.labels(direction="input").inc(result["input_tokens"])
        metrics.LLM_TOKENS.labels(direction="output").inc(result["output_tokens"])
        timings = dict(state.get("timings_ms", {}))
        timings["generation"] = round(elapsed_seconds * 1000)
        return {"answer": result["text"], "timings_ms": timings}

    async def no_context_node(state: AgentState) -> dict:
        """Nothing was retrieved, so skip the LLM call and say so."""
        timings = dict(state.get("timings_ms", {}))
        timings["generation"] = 0
        return {"answer": NO_CONTEXT_ANSWER, "timings_ms": timings}

    def route_after_retrieve(state: AgentState) -> str:
        """Branch: generate when we have context, otherwise short-circuit."""
        return "generate" if state.get("contexts") else "no_context"

    builder = StateGraph(AgentState)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("generate", generate_node)
    builder.add_node("no_context", no_context_node)

    builder.add_edge(START, "retrieve")
    builder.add_conditional_edges(
        "retrieve",
        route_after_retrieve,
        {"generate": "generate", "no_context": "no_context"},
    )
    builder.add_edge("generate", END)
    builder.add_edge("no_context", END)
    return builder.compile()
