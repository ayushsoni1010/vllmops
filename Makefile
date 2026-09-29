.PHONY: up up-local down down-v restart ps logs health key sync run lint fmt

# Auto-detect Docker Compose version.
# v2 ships as a Docker CLI plugin: "docker compose" (space)
# v1 ships as a standalone binary:  "docker-compose" (hyphen)
COMPOSE := $(shell docker compose version >/dev/null 2>&1 && echo "docker compose" || echo "docker-compose")

# ── Docker stack ───────────────────────────────────────────────────────────────

up:
	$(COMPOSE) up -d

# Mac / no-GPU local dev — skips vLLM (requires NVIDIA GPU).
# LiteLLM automatically falls back to Ollama on the host.
# Prerequisite: `ollama serve` must be running before this target.
up-local:
	@curl -sf http://localhost:11434 > /dev/null 2>&1 || \
		{ echo "ERROR: Ollama is not running. Start it with 'ollama serve' first."; exit 1; }
	@touch mlruns.db && mkdir -p mlruns
	$(COMPOSE) up -d --scale vllm=0

down:
	$(COMPOSE) down

down-v:
	$(COMPOSE) down -v

restart:
	$(COMPOSE) restart

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f

# Follow logs for a specific service: make logs-litellm
logs-%:
	$(COMPOSE) logs -f $*

# Check health of all services
health:
	$(COMPOSE) ps --format "table {{.Name}}\t{{.Status}}"

# ── LiteLLM virtual key ────────────────────────────────────────────────────────
# Generates a 30-day virtual key scoped to all models.
# Run once after `make up` to get a key for VLLM_API_KEY in .env.
key:
	@MASTER_KEY=$$(grep '^LITELLM_MASTER_KEY' .env | cut -d= -f2 | tr -d '"'); \
	curl -s -X POST http://localhost:4000/key/generate \
	  -H "Authorization: Bearer $$MASTER_KEY" \
	  -H "Content-Type: application/json" \
	  -d '{"models": ["qwen3-4b", "tinyllama", "gpt-4o-mini"], "duration": "30d"}' \
	  | python3 -m json.tool

# ── Python CLI ─────────────────────────────────────────────────────────────────

sync:
	uv sync

run:
	uv run llmops

# ── Code quality ───────────────────────────────────────────────────────────────

lint:
	uv run ruff check src/

fmt:
	uv run ruff format src/
