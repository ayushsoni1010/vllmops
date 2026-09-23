# vLLMOps

Production-grade LLMOps stack for self-hosted LLM inference. Combines vLLM (GPU inference), LiteLLM (AI gateway), nginx (reverse proxy), Prometheus + Grafana (observability), and MLflow (experiment tracking) — all wired together with Docker Compose.

## Architecture

```
Clients (any OpenAI-compatible SDK / REST)
          │
          ▼  :8000 (public)
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
| Ollama (optional) | Local fallback when GPU stack is not running |

## Quick Start

### 1. Clone and configure

```bash
git clone <repo-url>
cd vllmops
cp .env.example .env
# Fill in all placeholder values in .env
```

### 2. Start the stack

```bash
docker compose up -d
```

Services start in dependency order:
- Postgres and Redis come up first
- LiteLLM waits for Postgres to be healthy, then runs Prisma migrations
- nginx waits for LiteLLM to pass its health check

### 3. Verify

```bash
# LiteLLM gateway health
curl http://localhost:4000/health

# Test inference through the full stack
curl http://localhost:8000/v1/chat/completions \
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
| nginx | `0.0.0.0:8000` | Public API entry point |
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
| `OPENAI_API_KEY` | LiteLLM (optional) | Cloud fallback route |
| `GRAFANA_ADMIN_PASSWORD` | Grafana | UI login |
| `VLLM_API_BASE` | CLI | LiteLLM OpenAI-compatible endpoint |
| `VLLM_API_KEY` | CLI | Virtual key or master key for CLI requests |
| `VLLM_MODEL` | CLI | Model name as registered in `litellm/config.yaml` |
| `MLFLOW_TRACKING_URI` | CLI | Points autolog to the MLflow server |
| `PROMPT` | CLI | Default prompt (overridable) |

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
│   ├── cli.py               # main() — loads env, autologs MLflow, streams response
│   └── client.py            # build_llm() — ChatOpenAI pointed at LiteLLM
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
├── pyproject.toml
├── .env.example
└── ARCHITECTURE.md
```

## Stopping the Stack

```bash
docker compose down          # stop containers, keep volumes
docker compose down -v       # stop containers and delete all data volumes
```
