.PHONY: cluster argocd secret bootstrap ui-argocd ui-grafana ui-prometheus api load-test test

cluster:
	kind create cluster --name ai-platform

argocd:
	kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
	kubectl apply -n argocd --server-side -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
	kubectl -n argocd rollout status deploy/argocd-server --timeout=300s

# Secrets stay out of Git. Usage: make secret ANTHROPIC_API_KEY=sk-ant-...
secret:
	kubectl create namespace ai-platform --dry-run=client -o yaml | kubectl apply -f -
	kubectl -n ai-platform create secret generic anthropic-api-key \
		--from-literal=ANTHROPIC_API_KEY=$(ANTHROPIC_API_KEY) --dry-run=client -o yaml | kubectl apply -f -

bootstrap:
	kubectl apply -f argocd/root-app.yaml

ui-argocd:
	@echo "user: admin  password:" && kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d && echo
	kubectl -n argocd port-forward svc/argocd-server 8080:443

ui-grafana:
	kubectl -n monitoring port-forward svc/kps-grafana 3000:80

ui-prometheus:
	kubectl -n monitoring port-forward svc/kps-prometheus 9090:9090

api:
	kubectl -n ai-platform port-forward svc/gateway 8000:8000

load-test:
	python3 scripts/load_test.py --url http://localhost:8000/ask --duration 120 --concurrency 20

test:
	cd services/gateway && pytest -q
	cd services/agent && pytest -q
