.PHONY: help dev up down build test lint fmt clean seed demo gateway ui \
        docs docs-dev observability observability-down oidc oidc-down \
        policy-publish redteam compliance-report bench-perf bench-soak eval \
        edge-proxy-build edge-proxy-test browser-build browser-test \
        vscode-build vscode-test jetbrains-build jetbrains-test \
        edge-build edge-test

help:
	@echo "Section — common tasks"
	@echo "  make dev               — bring up full stack via docker compose"
	@echo "  make up                — alias for dev"
	@echo "  make down              — stop the stack"
	@echo "  make build             — build all images"
	@echo "  make gateway           — run gateway locally (no docker)"
	@echo "  make ui                — run UI locally (no docker)"
	@echo "  make test              — run all tests"
	@echo "  make lint              — lint python + ts"
	@echo "  make fmt               — auto-format"
	@echo "  make seed              — load demo policies"
	@echo "  make demo              — end-to-end demo script"
	@echo "  make docs              — build static docs site -> docs-site/dist"
	@echo "  make docs-dev          — run docs site locally on :4321"
	@echo "  make observability     — start full stack + Grafana/Prom/Tempo/Loki"
	@echo "  make observability-down— stop observability overlay"
	@echo "  make oidc              — start full stack + Keycloak (dev OIDC)"
	@echo "  make oidc-down         — stop OIDC overlay"
	@echo "  make policy-publish    — sign + push examples/policies to OCI"
	@echo "  make redteam           — run scripts/redteam/run.sh"
	@echo "  make compliance-report — generate Markdown+PDF report (TENANT=acme DAYS=90)"
	@echo "  make edge-build        — build edge-proxy + browser + vscode + jetbrains"
	@echo "  make edge-test         — run all edge-client test suites"
	@echo "  make edge-proxy-build  — build section-edge-proxy wheel"
	@echo "  make browser-build     — build the MV3 browser extension (.zip + .crx)"
	@echo "  make vscode-build      — package the VS Code .vsix"
	@echo "  make jetbrains-build   — gradle buildPlugin (requires jdk 17+, gradle)"
	@echo "  make bench-perf        — gateway latency baseline (in-process ASGI, ~1 min)"
	@echo "  make bench-soak        — Locust soak (SOAK_DURATION=1h SOAK_RPS=100 by default)"
	@echo "  make eval              — DLP detector coverage eval (precision/recall/F1)"
	@echo "  make clean             — remove caches and build artefacts"

dev up:
	docker compose up --build

down:
	docker compose down

build:
	docker compose build

gateway:
	cd services/gateway && uv run uvicorn section_gateway.main:app --reload --port 8080

ui:
	cd services/ui && pnpm dev

test:
	cd services/gateway && uv run pytest -q
	cd services/ui && pnpm test --if-present

lint:
	cd services/gateway && uv run ruff check .
	cd services/ui && pnpm lint

fmt:
	cd services/gateway && uv run ruff format .
	cd services/ui && pnpm format

seed:
	uv run python scripts/seed_policies.py

demo:
	bash scripts/demo.sh

docs:
	cd docs-site && pnpm install --frozen-lockfile || pnpm install
	cd docs-site && pnpm build

docs-dev:
	cd docs-site && pnpm install --frozen-lockfile || pnpm install
	cd docs-site && pnpm dev

observability:
	docker compose -f docker-compose.yml -f docker-compose.observability.yml up --build

observability-down:
	docker compose -f docker-compose.yml -f docker-compose.observability.yml down

oidc:
	docker compose -f docker-compose.yml -f docker-compose.oidc.yml up --build

oidc-down:
	docker compose -f docker-compose.yml -f docker-compose.oidc.yml down

policy-publish:
	bash scripts/policy_publish.sh

redteam:
	bash scripts/redteam/run.sh

# Generate a compliance report.
#   make compliance-report TENANT=acme DAYS=90
TENANT ?= default
DAYS ?= 90
compliance-report:
	mkdir -p dist/compliance
	uv run python scripts/compliance_report.py \
	  --tenant $(TENANT) --days $(DAYS) \
	  --out dist/compliance/$(TENANT)-$(shell date -u +%Y%m%d)

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +
	find . -type d -name .ruff_cache -prune -exec rm -rf {} +
	rm -rf services/ui/.next services/ui/node_modules/.cache

# --- Benchmarks & eval ------------------------------------------------------
# Extra deps live in bench/requirements.txt — install with
# `python -m pip install -r bench/requirements.txt` before `bench-soak`.

bench-perf:
	bash bench/perf/run.sh

bench-soak:
	bash bench/soak/run-soak.sh

eval:
	cd services/gateway && uv run python ../../bench/eval/run_eval.py

# --- Edge clients (1.1) -----------------------------------------------------

edge-proxy-build:
	cd services/edge-proxy && uv build

edge-proxy-test:
	cd services/edge-proxy && uv run pytest -q

browser-build:
	cd clients/browser && npm install && npm run build && npm run build:zip

browser-test:
	cd clients/browser && npm test && npm run typecheck

vscode-build:
	cd clients/vscode && npm install && npm run build && npm run package

vscode-test:
	cd clients/vscode && npm test && npm run typecheck

jetbrains-build:
	cd clients/jetbrains && ./gradlew buildPlugin

jetbrains-test:
	cd clients/jetbrains && ./gradlew test

edge-build: edge-proxy-build browser-build vscode-build jetbrains-build

edge-test: edge-proxy-test browser-test vscode-test jetbrains-test
