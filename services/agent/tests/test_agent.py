import asyncio

import pytest
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from app import config, llm, main, retrieval
from app.graph import NO_CONTEXT_ANSWER, build_graph

FAKE_CONTEXTS = [
    {"title": "Kubernetes Pod", "content": "A Pod is the smallest deployable unit.", "distance": 0.10},
    {"title": "Kubernetes Deployment", "content": "A Deployment manages ReplicaSets.", "distance": 0.20},
]


def sample(name: str, labels: dict | None = None) -> float:
    """Read one metric sample, treating a missing series as zero."""
    return REGISTRY.get_sample_value(name, labels or {}) or 0.0


def make_graph(contexts, answer_text="Answer. [Kubernetes Pod]", generate_error=None, search_error=None):
    """Build a graph around fake search and generate functions."""

    def fake_search(query, top_k):
        if search_error:
            raise search_error
        return contexts

    async def fake_generate(question, found_contexts):
        if generate_error:
            raise generate_error
        return {"text": answer_text, "input_tokens": 120, "output_tokens": 30}

    return build_graph(fake_search, fake_generate)


def test_graph_generates_answer_and_records_metrics():
    graph = make_graph(FAKE_CONTEXTS)
    input_before = sample("agent_llm_tokens_total", {"direction": "input"})
    output_before = sample("agent_llm_tokens_total", {"direction": "output"})

    state = asyncio.run(graph.ainvoke({"question": "What is a Pod?"}))

    assert state["answer"] == "Answer. [Kubernetes Pod]"
    assert set(state["timings_ms"]) == {"retrieval", "generation"}
    assert sample("agent_llm_tokens_total", {"direction": "input"}) == input_before + 120
    assert sample("agent_llm_tokens_total", {"direction": "output"}) == output_before + 30


def test_graph_skips_llm_when_nothing_is_retrieved():
    graph = make_graph([], generate_error=AssertionError("LLM must not be called"))

    state = asyncio.run(graph.ainvoke({"question": "What is a Pod?"}))

    assert state["answer"] == NO_CONTEXT_ANSWER
    assert state["timings_ms"]["generation"] == 0


def test_graph_counts_llm_errors():
    graph = make_graph(FAKE_CONTEXTS, generate_error=RuntimeError("provider down"))
    before = sample("agent_llm_errors_total")

    with pytest.raises(RuntimeError):
        asyncio.run(graph.ainvoke({"question": "What is a Pod?"}))

    assert sample("agent_llm_errors_total") == before + 1


def test_run_endpoint_returns_answer_with_sources(monkeypatch):
    monkeypatch.setattr(main, "graph", make_graph(FAKE_CONTEXTS))
    client = TestClient(main.app)
    before = sample("agent_requests_total", {"status": "ok"})

    response = client.post("/run", json={"question": "What is a Pod?"})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"].startswith("Answer.")
    assert [source["title"] for source in body["sources"]] == ["Kubernetes Pod", "Kubernetes Deployment"]
    assert sample("agent_requests_total", {"status": "ok"}) == before + 1


def test_run_returns_503_when_knowledge_base_not_ready(monkeypatch):
    graph = make_graph([], search_error=retrieval.KnowledgeBaseNotReady("no table"))
    monkeypatch.setattr(main, "graph", graph)
    client = TestClient(main.app)

    response = client.post("/run", json={"question": "What is a Pod?"})

    assert response.status_code == 503
    assert sample("agent_requests_total", {"status": "kb_not_ready"}) >= 1


def test_run_returns_503_when_llm_unavailable(monkeypatch):
    graph = make_graph(FAKE_CONTEXTS, generate_error=llm.LLMUnavailable("ANTHROPIC_API_KEY is not set"))
    monkeypatch.setattr(main, "graph", graph)
    client = TestClient(main.app)

    response = client.post("/run", json={"question": "What is a Pod?"})

    assert response.status_code == 503
    assert "ANTHROPIC_API_KEY" in response.json()["detail"]


def test_echo_mode_spends_no_tokens(monkeypatch):
    monkeypatch.setattr(config, "LLM_MODE", "echo")

    result = asyncio.run(llm.generate_answer("What is a Pod?", FAKE_CONTEXTS))

    assert "Kubernetes Pod" in result["text"]
    assert result["input_tokens"] == 0 and result["output_tokens"] == 0


def test_anthropic_mode_without_key_raises(monkeypatch):
    monkeypatch.setattr(config, "LLM_MODE", "anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    llm._get_client.cache_clear()

    with pytest.raises(llm.LLMUnavailable):
        asyncio.run(llm.generate_answer("What is a Pod?", FAKE_CONTEXTS))


def test_prompt_contains_context_and_question():
    prompt = llm.build_prompt("What is a Pod?", FAKE_CONTEXTS)

    assert "[Kubernetes Pod]" in prompt
    assert "smallest deployable unit" in prompt
    assert prompt.endswith("Question: What is a Pod?")


def test_vector_literal_format():
    assert retrieval.to_vector_literal([0.5, -1.0, 0.25]) == "[0.500000,-1.000000,0.250000]"


def test_metrics_endpoint_exposes_agent_series():
    client = TestClient(main.app)

    body = client.get("/metrics").text

    for name in ["agent_requests_total", "agent_retrieval_seconds", "agent_llm_seconds", "agent_llm_tokens_total"]:
        assert name in body
