"""Small async load generator for the gateway. Needs: pip install httpx.
Run with the cluster in LLM_MODE=echo to measure the platform, not the LLM provider."""
import argparse, asyncio, random, statistics, time
import httpx

QUESTIONS = [
    "What does Argo CD selfHeal do?",
    "How does a HorizontalPodAutoscaler decide to scale?",
    "What is pgvector cosine distance?",
    "Why use a PostSync hook?",
    "What does histogram_quantile compute?",
    "How does Grafana load dashboards from ConfigMaps?",
]

async def worker(client, url, deadline, lat, errors):
    while time.monotonic() < deadline:
        t = time.monotonic()
        try:
            r = await client.post(url, json={"question": random.choice(QUESTIONS)})
            (lat if r.status_code == 200 else errors).append(time.monotonic() - t if r.status_code == 200 else r.status_code)
        except httpx.HTTPError as e:
            errors.append(type(e).__name__)

async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://localhost:8000/ask")
    p.add_argument("--duration", type=int, default=120)
    p.add_argument("--concurrency", type=int, default=20)
    a = p.parse_args()
    lat, errors = [], []
    deadline = time.monotonic() + a.duration
    async with httpx.AsyncClient(timeout=60) as c:
        await asyncio.gather(*[worker(c, a.url, deadline, lat, errors) for _ in range(a.concurrency)])
    if not lat:
        print("no successful requests; errors:", errors[:5]); return
    lat.sort()
    q = lambda f: lat[min(len(lat) - 1, int(len(lat) * f))]
    print(f"requests ok={len(lat)} errors={len(errors)} rps={len(lat)/a.duration:.1f}")
    print(f"latency p50={q(.5)*1000:.0f}ms p95={q(.95)*1000:.0f}ms p99={q(.99)*1000:.0f}ms mean={statistics.mean(lat)*1000:.0f}ms")

asyncio.run(main())
