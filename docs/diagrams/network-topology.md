# Network Topology

Docker network isolation: which containers live on which network, and what host ports are bound.

```mermaid
graph TB
    subgraph host["Host Machine"]
        subgraph pub["public network (bridge)"]
            nginx["nginx\nhost :8000 → container :80"]
        end

        subgraph int["internal network (bridge)"]
            litellm["LiteLLM\n127.0.0.1:4000 → container :4000"]
            vllm["vLLM\nno host port\ninternal :8000 only"]
            redis["Redis\nno host port\ninternal :6379 only"]
            postgres["PostgreSQL\nno host port\ninternal :5432 only"]
            prometheus["Prometheus\n127.0.0.1:9090 → container :9090"]
            grafana["Grafana\n127.0.0.1:3000 → container :3000"]
            mlflow["MLflow\n127.0.0.1:5000 → container :5000"]
        end

        ollama["Ollama\nhost.docker.internal:11434\n(native process, not in Docker)"]
    end

    internet["🌐 Internet / Client"]
    browser["🖥 Ops Browser\n(host only — 127.0.0.1)"]

    internet -->|":8000"| nginx
    nginx --> litellm

    litellm --> vllm
    litellm --> redis
    litellm --> postgres
    litellm -.->|"host-gateway route"| ollama

    prometheus --> vllm
    prometheus --> litellm
    grafana --> prometheus

    browser -->|":4000 UI"| litellm
    browser -->|":9090"| prometheus
    browser -->|":3000"| grafana
    browser -->|":5000"| mlflow

    style pub fill:#d6eaf8,stroke:#2980b9
    style int fill:#d5f5e3,stroke:#27ae60
    style host fill:#fdfefe,stroke:#bdc3c7
```

## Port reference

| Service | Host binding | Purpose |
|---|---|---|
| nginx | `0.0.0.0:8000` | Public API entry point |
| LiteLLM | `127.0.0.1:4000` | Ops UI + key management |
| Prometheus | `127.0.0.1:9090` | Metrics UI |
| Grafana | `127.0.0.1:3000` | Dashboards |
| MLflow | `127.0.0.1:5000` | Experiment tracking |
| vLLM | *none* | Internal only — no direct access |
| Redis | *none* | Internal only |
| PostgreSQL | *none* | Internal only |

Observability ports are bound to `127.0.0.1` — reachable from the host browser but not the LAN.
