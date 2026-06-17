.PHONY: dev mock-openclaw server voice api test test-cov lint lint-fix \
        clean setup seed dashboard dashboard-build dashboard-setup check-openclaw help

# ── Development (no API keys needed) ──────────────────────────
dev: ## Run Orion in text mode with mock OpenClaw (no API keys needed)
	DEV_MODE=true MOCK_OPENCLAW=true uv run python dev/text_agent.py

mock-openclaw: ## Start the mock OpenClaw server on port 18789
	uv run python dev/mock_openclaw.py

seed: ## Seed the database with sample data
	uv run python dev/seed_db.py

# ── Production processes ───────────────────────────────────────
server: ## Start the FastMCP tool server (port 8000)
	uv run orion_server

voice: ## Start the LiveKit voice agent
	uv run orion_voice

api: ## Start the FastAPI runtime API (port 8010)
	uv run orion_api

# ── Frontend dashboard ─────────────────────────────────────────
dashboard-setup: ## Install dashboard dependencies
	cd dashboard && npm install

dashboard: ## Start the dashboard dev server
	cd dashboard && npx vite

dashboard-build: ## Build the dashboard for production
	cd dashboard && npm run build

# ── Quality & testing ──────────────────────────────────────────
test: ## Run all tests
	uv run pytest tests/ -v

test-cov: ## Run tests with coverage report
	uv run pytest tests/ -v --cov=orion --cov=bridge --cov-report=term-missing

lint: ## Run linting and type checking
	uv run ruff check .
	uv run mypy orion/ bridge/

lint-fix: ## Auto-fix linting issues
	uv run ruff check . --fix

# ── Setup ──────────────────────────────────────────────────────
setup: ## Initial project setup — install deps and create .env
	cp -n .env.example .env 2>/dev/null || true
	uv sync
	@echo ""
	@echo "╔══════════════════════════════════════════════╗"
	@echo "║            Setup complete!                   ║"
	@echo "╠══════════════════════════════════════════════╣"
	@echo "║  For dev (no API keys):  make dev            ║"
	@echo "║  For production:         edit .env            ║"
	@echo "║                          then make server     ║"
	@echo "╚══════════════════════════════════════════════╝"

# ── Utilities ──────────────────────────────────────────────────
check-openclaw: ## Check if the OpenClaw daemon is running
	openclaw gateway status

clean: ## Remove cached files and build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	find . -name ".coverage" -delete 2>/dev/null || true
	@echo "Cleaned."

help: ## Show this help message
	@echo "Available targets:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
