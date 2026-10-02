# Claude Code — Project Guide

## What this project is

A production-grade LLMOps stack for self-hosted vLLM inference. Four separate surfaces:

1. **Docker stack** — nginx → LiteLLM → vLLM + Redis + Postgres + Prometheus + Grafana + MLflow
2. **Python CLI** (`uv run llmops`) — renders a Jinja2 prompt template, streams through LiteLLM, logs traces + artifacts to MLflow
3. **Eval harness** (`uv run pytest tests/evals/`) — golden regression suite; pattern-asserts model output and logs per-case runs to `vllmops-evals` MLflow experiment
4. **Model registry** (`uv run llmops-register`) — registers vLLM serving configs as MLflow model versions; tracks base model + quantization + adapter per variant; promotes via aliases (champion/challenger)

## Key commands

```bash
# CLI
uv run llmops                        # run the entry point
uv run llmops-register               # register a vLLM serving config as a model version
uv sync --all-groups                 # install / sync all dependencies (including dev)

# Eval harness
uv run pytest tests/evals/ -v        # run golden eval suite (requires live stack)

# Docker stack (requires Linux + NVIDIA GPU)
docker compose up -d                 # start all services
docker compose down                  # stop, keep volumes
docker compose logs -f litellm       # follow a specific service
docker compose ps                    # check health status
```

## Project structure

```
src/llmops/
  __init__.py    re-exports main — touch only if adding public API
  cli.py         load_dotenv() at module level; main(): set_experiment → openai_autolog → collect_vars/render → uuid4 correlation_id → build_llm → start_run → set_tags → log_params → log_artifacts(prompts/) → stream → log_metrics(latency_ms, output_chars, prompt_tokens, completion_tokens, cost_usd)
  client.py      build_llm(): ChatOpenAI pointed at VLLM_API_BASE; stream_usage=True requests token counts from backend
  cost.py        compute_cost(prompt_tokens, completion_tokens): PROMPT_TOKEN_COST + COMPLETION_TOKEN_COST rates → cost_usd
  prompts.py     collect_vars(), render(), log_artifacts() — Jinja2 template loading and MLflow artifact logging
  registry.py    register(): standalone entry point — creates vllmops-registry MLflow run, logs serving_config.json, registers model version, optionally sets alias
  feedback.py    collect(): called after every inference run — logs feedback metric (1.0=good/0.0=bad) and feedback_label tag to the active run; interactive prompt when TTY, env-var override for CI

prompts/               versioned Jinja2 prompt templates (.j2 files)
  default.j2           default template; variables injected from PROMPT_VAR_* env vars

tests/evals/
  conftest.py          session-scoped llm fixture; sets vllmops-evals MLflow experiment
  fixtures/
    golden.yaml        eval cases: template + variables + expected_patterns + max_latency_ms
  test_golden.py       parametrized pytest; per-case MLflow run with artifacts + passed metric

litellm/config.yaml   model registry, fallback chain, Redis cache config
nginx/default.conf.template   reverse proxy; no auth (LiteLLM owns auth)
prometheus/prometheus.yml     scrape targets: vllm + litellm
grafana/dashboards/           provisioned dashboard JSON
docker-compose.yml            full service graph
pyrightconfig.json    points pyright at .venv for import resolution
.env / .env.example           all runtime secrets and config
```

## Environment variables

All required vars are in `.env`. The pattern is fail-loud (`os.environ["KEY"]` not `.get()`):
- `VLLM_API_BASE` — LiteLLM OpenAI endpoint the CLI hits
- `VLLM_API_KEY` — virtual key or master key
- `VLLM_MODEL` — must match a `model_name` in `litellm/config.yaml`
- `MLFLOW_TRACKING_URI` — MLflow server URL for the tracking client
- `RUN_USER` — username stamped on every MLflow run (`mlflow.user` tag); required, fail-loud
- `RUN_EMAIL` — email stamped on every MLflow run (`user.email` tag); required, fail-loud
- `REDIS_PASSWORD` — Redis auth password; required by both redis-server and LiteLLM cache
- `LITELLM_WORKERS` — number of LiteLLM workers (default `2` via compose; set explicitly in `.env`)
- `MLFLOW_EXPERIMENT` — MLflow experiment name (optional; default `"vllmops"`)
- `APP_ENV` — deployment environment tag on runs: `dev` / `staging` / `prod` (optional; default `"dev"`)
- `PROMPT_TEMPLATE` — name of the template file in `prompts/` without `.j2` (optional; default `"default"`)
- `PROMPT_VAR_*` — variables injected into the Jinja2 template at render time (e.g. `PROMPT_VAR_TOPIC=LLMOps`); collected automatically by prefix scan
- `PROMPTS_DIR` — override path to the prompts directory (optional; default `./prompts` relative to CWD)
- `PROMPT_TOKEN_COST` — USD per prompt token for `cost_usd` metric (optional; default `0.0` — self-hosted has no market rate)
- `COMPLETION_TOKEN_COST` — USD per completion token for `cost_usd` metric (optional; default `0.0`)
- `FEEDBACK` — human label for the current run: `good` or `bad` (optional; if unset and stdin is a TTY, the CLI prompts interactively after streaming; non-TTY/CI with no value = no-op)
- `MLFLOW_REGISTER_MODEL` — registered model name for `llmops-register` (required when running that command; e.g. `"qwen3-4b-awq"`)
- `MODEL_QUANTIZATION` — declared quantization variant (optional; e.g. `"awq"`, `"gptq"`, `"fp16"`) — stored as metadata, not validated against vLLM
- `MODEL_ADAPTER` — declared LoRA adapter path or HF hub name (optional) — stored as metadata
- `MODEL_ALIAS` — alias to set on the newly registered version (optional; e.g. `"champion"`, `"challenger"`)

## Conventions

**Python code**
- No try/except around `os.environ["KEY"]` — missing env vars must fail loudly
- No default fallbacks for required config — if a key is wrong, it should crash, not silently use a wrong value
- `__init__.py` is a re-export only — no logic there
- Business logic lives in `cli.py` (orchestration), `client.py` (LLM construction), and `prompts.py` (template rendering)
- No argparse / click — config is env-driven
- Streaming via `.stream()`, not `.invoke()` — never buffer a full LLM response in the CLI
- Eval tests use `.invoke()` — the stream-only rule is for the CLI; tests need the full output to assert patterns

**Docker / infrastructure**
- All inter-service traffic is on the `internal` Docker network
- vLLM has no host ports — only reachable via LiteLLM
- Observability ports (9090, 3000, 5000, 4000) bind to `127.0.0.1` — not LAN-accessible
- Auth belongs in LiteLLM, not nginx — nginx is a stateless proxy
- `nginx/default.conf.template` is the active config; `nginx/nginx.conf` is the old broken file and can be deleted
- `scrape_timeout` must be < `scrape_interval` in Prometheus config

**LiteLLM**
- Model names in `litellm/config.yaml` are the virtual names clients send
- Add vLLM nodes by repeating a `model_name` entry with a different `api_base`
- Fallback order: vLLM GPU → Ollama (host) → OpenAI cloud (if `OPENAI_API_KEY` set)

## What not to do

- Do not add auth logic to nginx — LiteLLM manages all API keys
- Do not expose vLLM ports to the host — it has no auth
- Do not use `scrape_timeout >= scrape_interval` in Prometheus
- Do not add a dual-backend abstraction to the CLI — keep it env-driven and single-path
- Do not commit `.env` — it is gitignored; only `.env.example` is tracked
- Do not commit `mlflow.db` — add it to `.gitignore` if it appears
- Do not commit `mlruns.db` or `mlruns/` — both are gitignored; they are bind-mounted into the MLflow container
- Do not add `addopts = "-m 'not eval'"` to `[tool.pytest.ini_options]` — it silently deselects all cases when running `uv run pytest tests/evals/`
- Do not tighten eval patterns for the fallback backend (tinyllama hallucinates freely); keep patterns broad enough to survive creative paraphrasing
- Do not set `FEEDBACK=good` permanently in `.env` — it would stamp every run as good regardless of output quality; leave it commented out and set it per-run
- Do not call `registry.register()` from inside the inference CLI — registration is a deliberate per-variant operation, not a per-prompt side-effect; run `llmops-register` explicitly when you have a new adapter or quantization variant
- Do not expect `mlflow.pyfunc.load_model()` to work on registered versions — the registry is a config catalog, not a model store; weights live in vLLM
