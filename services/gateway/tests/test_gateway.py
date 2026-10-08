import httpx
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from app import main

client = TestClient(main.app)

FAKE_AGENT_RESULT = {
    "answer": "A Pod is the smallest deployable unit. [Kubernetes Pod]",
    "sources": [{"title": "Kubernetes Pod", "distance": 0.12}],
    "timings_ms": {"retrieval": 20, "generation": 900},
}


def sample(name: str, labels: dict) -> float:
    """Read one metric sample, treating a missing series as zero."""
    return REGISTRY.get_sample_value(name, labels) or 0.0


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ask_returns_agent_answer(monkeypatch):
    async def fake_call_agent(question: str) -> dict:
        return FAKE_AGENT_RESULT

    monkeypatch.setattr(main, "call_agent", fake_call_agent)
    before = sample("gateway_requests_total", {"route": "/ask", "status": "200"})

    response = client.post("/ask", json={"question": "What is a Pod?"})

    assert response.status_code == 200
    assert response.json()["sources"][0]["title"] == "Kubernetes Pod"
    after = sample("gateway_requests_total", {"route": "/ask", "status": "200"})
    assert after == before + 1


def test_ask_rejects_short_question():
    response = client.post("/ask", json={"question": "hi"})
    assert response.status_code == 422


def test_agent_connection_error_becomes_502(monkeypatch):
    async def failing_call_agent(question: str) -> dict:
        raise httpx.ConnectError("agent down")

    monkeypatch.setattr(main, "call_agent", failing_call_agent)
    before = sample("gateway_upstream_errors_total", {"kind": "connection"})

    response = client.post("/ask", json={"question": "What is a Pod?"})

    assert response.status_code == 502
    assert sample("gateway_upstream_errors_total", {"kind": "connection"}) == before + 1


def test_metrics_endpoint_exposes_expected_series(monkeypatch):
    async def fake_call_agent(question: str) -> dict:
        return FAKE_AGENT_RESULT

    monkeypatch.setattr(main, "call_agent", fake_call_agent)
    client.post("/ask", json={"question": "What is a Pod?"})

    body = client.get("/metrics").text

    assert "gateway_requests_total" in body
    assert "gateway_request_seconds_bucket" in body
    assert 'route="/ask"' in body
