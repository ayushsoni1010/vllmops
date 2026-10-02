# CLI Flow — `uv run llmops`

How the Python CLI processes a prompt and records the trace.

```mermaid
sequenceDiagram
    autonumber
    participant U  as User (terminal)
    participant C  as cli.py (module level)
    participant M  as main()
    participant P  as prompts.py
    participant B  as client.py (build_llm)
    participant ML as MLflow Server<br/>localhost:5000
    participant L  as LiteLLM Gateway<br/>localhost:4000 (via nginx :80)
    participant V  as vLLM / Ollama

    U  ->> C  : uv run llmops
    note over C : load_dotenv() runs at module level<br/>before mlflow is imported<br/>(ensures MLFLOW_DISABLE_AGENT_HINT is set)
    C  ->> ML : openai_autolog() — patches openai SDK<br/>to capture traces automatically

    C  ->> M  : main()
    M  ->> ML : mlflow.set_experiment(MLFLOW_EXPERIMENT)
    M  ->> P  : collect_vars() → {topic: "LLMOps", ...}
    M  ->> P  : render(PROMPT_TEMPLATE, variables) → prompt string
    note over P : Jinja2 loads prompts/<name>.j2<br/>substitutes PROMPT_VAR_* variables<br/>StrictUndefined — missing vars crash loudly
    M  ->> M  : correlation_id = str(uuid4())
    M  ->> B  : build_llm(extra_headers={"X-Correlation-ID": correlation_id})
    B  -->> M : ChatOpenAI(base_url=VLLM_API_BASE, default_headers=...)

    M  ->> ML : mlflow.start_run()
    M  ->> ML : set_tags(_build_run_tags(correlation_id))<br/>mlflow.user · user.email · env · app.version<br/>run.correlation_id · git.commit (CI only)
    M  ->> ML : log_params(model · api_base · prompt_template · prompt_chars · prompt_var.*)
    M  ->> ML : log_artifacts(prompts/)<br/>rendered.txt · variables.json · <name>.j2

    M  ->> M  : t0 = time.monotonic(); output_chars = 0<br/>prompt_tokens = 0; completion_tokens = 0
    M  ->> L  : llm.stream([HumanMessage(prompt)])<br/>stream_usage=True — backend returns token counts<br/>X-Correlation-ID header forwarded to LiteLLM logs
    L  ->> V  : forward to vLLM (primary) or Ollama (fallback)

    loop Token streaming
        V  -->> L  : token chunk (+ usage_metadata on one chunk)
        L  -->> M  : AIMessageChunk
        M  ->> M  : output_chars += len(chunk.content)<br/>if chunk.usage_metadata → capture prompt/completion tokens
        M  -->> U  : print(chunk.content, end="", flush=True)
    end

    M  ->> M  : latency_ms = (monotonic() - t0) * 1000<br/>cost_usd = compute_cost(prompt_tokens, completion_tokens)
    M  ->> ML : log_metrics(latency_ms · output_chars · prompt_tokens · completion_tokens · cost_usd)
    ML -->> ML : openai_autolog flushes trace<br/>POST /api/3.0/mlflow/traces
    note over U,ML : Run visible at http://localhost:5000
```

## Routing and observability

The CLI always uses `ChatOpenAI` pointed at `VLLM_API_BASE` (the LiteLLM gateway through nginx). There is no separate local-dev code path — LiteLLM handles backend selection (vLLM GPU → Ollama fallback) transparently.

The `run.correlation_id` tag on the MLflow run matches the `X-Correlation-ID` header forwarded to LiteLLM, letting you join the MLflow run to LiteLLM's Postgres usage logs and nginx access logs on the same UUID.

## Prompt template system

Prompts live in `prompts/<name>.j2` as versioned Jinja2 templates. Variables are passed via `PROMPT_VAR_<KEY>=value` env vars and injected at render time. Every MLflow run stores three artifacts under `prompts/`:

| Artifact | Contents |
|---|---|
| `prompts/<name>.j2` | Raw template source — exact version used |
| `prompts/rendered.txt` | Final prompt sent to the model |
| `prompts/variables.json` | Variable bindings used for rendering |

This makes every run fully reproducible: re-render the logged template with the logged variables to get the exact prompt. A/B testing a prompt change is a first-class operation: branch the template, run both, compare `latency_ms` and quality metrics in MLflow side-by-side.

| What is logged | Where | How |
|---|---|---|
| `model`, `api_base`, `prompt_template`, `prompt_chars`, `prompt_var.*` | MLflow params | `mlflow.log_params()` |
| `latency_ms`, `output_chars`, `prompt_tokens`, `completion_tokens`, `cost_usd` | MLflow metrics | `mlflow.log_metrics()` |
| `mlflow.user`, `user.email`, `env`, `app.version`, `run.correlation_id` | MLflow tags | `mlflow.set_tags()` |
| Template source, rendered prompt, variables | MLflow artifacts (`prompts/`) | `mlflow.log_artifacts()` |
| Full trace (inputs · outputs · spans) | MLflow Traces tab | `openai_autolog()` |

## Cost tracking

`prompt_tokens` and `completion_tokens` are captured from `AIMessageChunk.usage_metadata` during streaming — enabled by `stream_usage=True` on `ChatOpenAI`. `cost_usd` is computed by `cost.compute_cost()` using configurable per-token USD rates:

| Env var | Default | Purpose |
|---|---|---|
| `PROMPT_TOKEN_COST` | `0.0` | USD per prompt token |
| `COMPLETION_TOKEN_COST` | `0.0` | USD per completion token |

Defaults to `0.0` for self-hosted inference (no cloud billing). Set to equivalent cloud pricing for cost attribution across teams or experiments.
