# vLLMOps

Production-grade LLMOps stack for self-hosted LLM inference. Combines vLLM (GPU inference), LiteLLM (AI gateway), nginx (reverse proxy), Prometheus + Grafana (observability), and MLflow (experiment tracking) — all wired together with Docker Compose.

## Architecture

```
Clients (any OpenAI-compatible SDK / REST)
          │
          ▼  :80 (public)
   ┌─────────────┐
   │    nginx    │  reverse proxy · TLS termination
   └──────┬──────┘
          │  (internal network)
          ▼  :4000
   ┌──────────────────┐
   │     LiteLLM      │  auth · rate limiting · routing
   │    AI Gateway    │  retry · fallback · cost tracking
   └──┬───────────────┘
      │
      ├────────────────────────────────┐
      ▼                                ▼
   ┌────────┐                    ┌──────────┐
   │  Redis │                    │ Postgres │
   │ cache  │                    │ keys /   │
   │ limits │                    │ budgets  │
   └────────┘                    └──────────┘
      │
      ├──────────────────────────┐
      ▼  :8000 (internal only)   ▼  host:11434 (fallback)
   ┌──────────────┐        ┌───────────┐
   │  vLLM (GPU)  │        │   Ollama  │
   │  Qwen3-4B    │        │ tinyllama │
   └──────────────┘        └───────────┘

Observability  (localhost-only ports)
   Prometheus  :9090  →  scrapes vllm + litellm
   Grafana     :3000  →  dashboards
   MLflow      :5000  →  experiment tracking (CLI)
```

## Prerequisites

| Requirement | Notes |
|---|---|
| Docker + Docker Compose | Engine 20.10+ |
| NVIDIA GPU | A100 / H100 recommended for Qwen3-4B |
| NVIDIA Container Toolkit | For GPU passthrough to vLLM |
| Hugging Face account | Token required for gated models |
| Python 3.12+ + uv | Local CLI only |
| Ollama | Required for `make up-local` (Mac/no-GPU dev); tinyllama must be pulled |

## Quick Start

### 1. Clone and configure

```bash
git clone <repo-url>
cd vllmops
cp .env.example .env
# Fill in all placeholder values in .env
```

### 2. Start the stack

**GPU server (Linux + NVIDIA):**
```bash
docker compose up -d
```

**Mac / local dev (no GPU):**
```bash
ollama serve              # must be running first
ollama pull tinyllama     # LiteLLM falls back to this
make up-local             # skips vLLM, fails fast if Ollama is unreachable
```

Services start in dependency order:
- Postgres and Redis come up first
- LiteLLM waits for Postgres to be healthy, then runs Prisma migrations
- nginx waits for LiteLLM to pass its health check

### 3. Verify

```bash
# LiteLLM gateway health
curl http://localhost:4000/health

# Test inference through the full stack (nginx :80 → LiteLLM → vLLM / Ollama)
curl http://localhost/v1/chat/completions \
  -H "Authorization: Bearer <VLLM_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"model": "qwen3-4b", "messages": [{"role": "user", "content": "Hello"}], "stream": true}'
```

### 4. Local CLI (no GPU required)

The CLI uses the LiteLLM gateway (OpenAI-compatible) and logs traces to MLflow.

```bash
uv sync
uv run llmops
```

Requires the Docker stack to be running (for LiteLLM at `:4000` and MLflow at `:5000`).

## Services & Ports

| Service | Host Port | Notes |
|---|---|---|
| nginx | `0.0.0.0:80` | Public API entry point |
| LiteLLM | `127.0.0.1:4000` | Gateway UI + virtual key management |
| Prometheus | `127.0.0.1:9090` | Metrics browser |
| Grafana | `127.0.0.1:3000` | Dashboards |
| MLflow | `127.0.0.1:5000` | Experiment tracking UI |
| vLLM | none | Internal only — reachable via LiteLLM |
| Redis | none | Internal only |
| Postgres | none | Internal only |

## Environment Variables

Copy `.env.example` to `.env` and fill in:

| Variable | Used by | Purpose |
|---|---|---|
| `HF_TOKEN` | vLLM | Download gated HuggingFace models |
| `LITELLM_MASTER_KEY` | LiteLLM | Admin key to create/revoke virtual keys |
| `POSTGRES_PASSWORD` | LiteLLM + Postgres | Database auth |
| `REDIS_PASSWORD` | Redis + LiteLLM | Redis auth; required by both server and cache client |
| `OPENAI_API_KEY` | LiteLLM (optional) | Cloud fallback route |
| `LITELLM_WORKERS` | LiteLLM | Number of gateway workers (default `2`) |
| `GRAFANA_ADMIN_PASSWORD` | Grafana | UI login |
| `VLLM_API_BASE` | CLI | LiteLLM OpenAI-compatible endpoint |
| `VLLM_API_KEY` | CLI | Virtual key or master key for CLI requests |
| `VLLM_MODEL` | CLI | Model name as registered in `litellm/config.yaml` |
| `MLFLOW_TRACKING_URI` | CLI | MLflow server URL for the tracking client |
| `MLFLOW_EXPERIMENT` | CLI | Experiment name (default `"vllmops"`) |
| `RUN_USER` | CLI | Username tag on every MLflow run; required |
| `RUN_EMAIL` | CLI | Email tag on every MLflow run; required |
| `APP_ENV` | CLI | Environment tag: `dev` / `staging` / `prod` (default `"dev"`) |
| `PROMPT_TEMPLATE` | CLI | Template name in `prompts/` (default `"default"`) |
| `PROMPT_VAR_*` | CLI | Variables injected into the template (e.g. `PROMPT_VAR_TOPIC=LLMOps`) |
| `PROMPTS_DIR` | CLI | Override path to the prompts directory (default `./prompts`) |

## Local Dev (Mac, no GPU)

`make up-local` starts all services except vLLM. LiteLLM routes requests through its fallback chain to Ollama running natively on the host.

```bash
# One-time setup
ollama pull tinyllama

# Every session
ollama serve          # must be running before make up-local
make up-local         # fails fast with a clear error if Ollama is unreachable

# Run the CLI
uv run llmops
```

Traffic path: `CLI → nginx :80 → LiteLLM → Ollama (host.docker.internal:11434)`

After `make down-v` (which wipes Postgres), virtual keys are gone. Set `VLLM_API_KEY` to `LITELLM_MASTER_KEY` temporarily, then run `make key` to create a scoped virtual key.

## Managing Virtual API Keys

LiteLLM handles all client authentication. Create virtual keys via the LiteLLM API using the master key:

```bash
curl -X POST http://localhost:4000/key/generate \
  -H "Authorization: Bearer <LITELLM_MASTER_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"models": ["qwen3-4b"], "max_budget": 10, "duration": "30d"}'
```

## Project Structure

```
vllmops/
├── src/llmops/
│   ├── __init__.py          # package re-export
│   ├── cli.py               # main() — renders prompt, autologs MLflow, streams response
│   ├── client.py            # build_llm() — ChatOpenAI pointed at LiteLLM
│   └── prompts.py           # collect_vars(), render(), log_artifacts() — Jinja2 templates
├── prompts/
│   └── default.j2           # default prompt template (PROMPT_VAR_* injected at render time)
├── tests/evals/
│   ├── conftest.py          # llm fixture, vllmops-evals MLflow experiment
│   ├── fixtures/golden.yaml # eval cases: template + variables + patterns + latency bound
│   └── test_golden.py       # parametrized pytest — pattern assertions + MLflow logging
├── litellm/
│   └── config.yaml          # model registry, routing, fallback, caching config
├── nginx/
│   └── default.conf.template  # reverse proxy; envsubst applied at container start
├── prometheus/
│   └── prometheus.yml       # scrape targets: vllm + litellm
├── grafana/
│   ├── dashboards/          # provisioned dashboard JSON + provider config
│   └── provisioning/datasources/  # Prometheus datasource
├── docker-compose.yml
├── pyrightconfig.json       # points pyright at .venv for import resolution
├── pyproject.toml
├── .env.example
└── ARCHITECTURE.md
```

## Evaluation

The golden eval harness validates model output quality against pattern-based assertions. Each case renders a prompt template, calls the model, checks the output, and logs results to the `vllmops-evals` MLflow experiment.

```bash
# Requires the Docker stack to be running (LiteLLM + MLflow)
uv run pytest tests/evals/ -v
```

Add new cases by editing `tests/evals/fixtures/golden.yaml` — no Python changes needed:

```yaml
cases:
  - id: my_new_case
    template: default
    variables:
      topic: Kubernetes
    expected_patterns:
      - "(?i)(container|orchestration|deploy|cluster|pod)"
    max_latency_ms: 60000
```

Each test run creates a separate MLflow run under `vllmops-evals` with `latency_ms`, `output_chars`, `passed` metric, `output.txt`, and the rendered prompt artifacts for full reproducibility.

## Stopping the Stack

```bash
docker compose down          # stop containers, keep volumes
docker compose down -v       # stop containers and delete all data volumes
```
