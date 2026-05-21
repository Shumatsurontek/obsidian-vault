.PHONY: help install lint format test \
	run-mcp run-mcp-http run-mcp-dev \
	run-agent run-api run-web \
	docker-build deploy

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-25s\033[0m %s\n", $$1, $$2}'

install: ## Install all workspace packages
	uv sync --all-packages

lint: ## Ruff check
	uv run ruff check .

format: ## Ruff format + fix
	uv run ruff format .
	uv run ruff check --fix .

test: ## Run all tests
	uv run pytest

# --- Obsidian MCP server ---
run-mcp: ## STDIO mode (Claude desktop client)
	uv run --package obsidian-mcp obsidian-mcp

run-mcp-http: ## HTTP mode on $PORT (default 8000)
	uv run --package obsidian-mcp obsidian-mcp --transport http --port $${PORT:-8000}

run-mcp-dev: ## With inspector
	uv run --package obsidian-mcp fastmcp dev obsidian_mcp/obsidian_mcp/server.py

# --- Agents ---
run-agent: ## Run the proactive organizer agent once
	uv run --package agents vault-organizer

# --- API + web ---
run-api: ## FastAPI dev server
	uv run --package api uvicorn api.main:app --reload --port $${PORT:-3001}

run-web: ## Next.js dev server
	cd web && npm run dev
