# AI Agent Platform on Kubernetes

A RAG question-answering agent (LangGraph + pgvector + Claude) deployed to Kubernetes with GitOps (Argo CD), autoscaled by an HPA, and observed with Prometheus and Grafana. Runs locally on `kind`.

```
git push -> GitHub Actions (test, multi-arch build, push to GHCR, bump image tag in deploy/overlays/local)
                                      |
                                      v
                 Argo CD (app of apps) watches this repo and syncs the cluster
                                      |
   +----------------------+-----------+--------------------+
   | kube-prometheus-stack |  metrics-server   |  ai-platform (Kustomize)      |
   | Prometheus + Grafana  |  (feeds the HPA)  |  gateway -> agent -> pgvector |
   +----------------------+--------------------+-------------------------------+
```
Measured in echo mode, so the Claude call is excluded. Latency is dominated by CPU embedding on a single-node kind cluster on a MacBook Air.

- **gateway** (FastAPI): validates `/ask`, forwards to the agent, records request rate, latency and errors.
- **agent** (FastAPI + LangGraph): `retrieve -> generate`, with a conditional edge to a no-context answer. Embeddings by fastembed (bge-small, 384 dims), vector search with pgvector (HNSW, cosine), answers by Claude.
- **Argo CD**: automated sync with prune and self-heal; sync waves install the monitoring CRDs before the app that uses them; a PostSync Job loads the knowledge base.
- **HPA**: agent 1 to 4 pods at 60% CPU, gateway 2 to 4 at 70%. `replicas` is deliberately omitted from the Deployments so Argo CD self-heal does not fight the autoscaler.
- **Observability**: ServiceMonitors, a PrometheusRule (p95 latency, 5xx rate, LLM errors) and a Grafana dashboard provisioned from a ConfigMap.

## Run it

Needs Docker Desktop, `brew install kind kubectl`, a Claude API key, and a GitHub repo named `ai-agent-platform`.

1. Push this folder to `github.com/sarvagna23/ai-agent-platform` (branch `main`). Let the Actions run finish, then make both GHCR packages (`ai-platform-gateway`, `ai-platform-agent`) **public** in the package settings, otherwise the cluster cannot pull them. Also allow workflow write access: Settings > Actions > General > Workflow permissions > Read and write.
2. `make cluster`
3. `make argocd`
4. `make secret ANTHROPIC_API_KEY=sk-ant-...`
5. `make bootstrap` and watch the apps turn green: `make ui-argocd` (https://localhost:8080)
6. `make api`, then `curl -X POST localhost:8000/ask -H 'content-type: application/json' -d '{"question":"What does Argo CD selfHeal do?"}'`
7. `make ui-grafana` (http://localhost:3000, admin / admin), dashboard "AI Agent Platform".

## Proof checklist (fill the results table only with numbers you measured)

- [ ] Argo CD shows `root`, `kube-prometheus-stack`, `metrics-server`, `ai-platform` Healthy and Synced.
- [ ] Self-heal: `kubectl -n ai-platform delete deploy gateway` and watch Argo CD recreate it.
- [ ] GitOps deploy: change code, push, see the new image tag roll out with no manual `kubectl`.
- [ ] Autoscaling: set `LLM_MODE` to `echo` in `deploy/base/agent.yaml` and push (editing the live cluster would be reverted by self-heal), then `make load-test` and watch `kubectl -n ai-platform get hpa -w` and the replicas panel.
- [ ] Alerts: the Prometheus `/alerts` page (`make ui-prometheus`) shows the three rules.

| Metric (echo mode, 20 concurrent users, 120 s) | Value |
|---|---|
| Throughput (req/s) | 17.9 (2,150 requests, 0 errors) |
| p50 / p95 latency | 1.10 s / 1.70 s (p99 1.90 s) |
| Agent replicas at peak | 4 (scaled from 1 by the HPA) |
| Time from `git push` to new pods serving | 511 s (about 8.5 min, includes the multi-arch CI build) |

## Known limits

- Helm chart versions are unpinned (`"*"`); pin tested versions before relying on this.
- The Postgres password is a dev-only value in Git; real setups use a secret manager (External Secrets, Sealed Secrets).
- Local only: single-node kind, `--kubelet-insecure-tls`, Grafana password `admin`, Alertmanager disabled.
- Manifests were checked for valid YAML and the services by unit tests; cluster behavior is verified only when you run it.
