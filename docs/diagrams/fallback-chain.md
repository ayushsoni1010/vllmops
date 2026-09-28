# Fallback Chain

How LiteLLM routes a request when the primary backend is unavailable.

```mermaid
flowchart TD
    A([Request arrives at LiteLLM]) --> B{Virtual key valid\n& under budget?}

    B -->|No| Z1([401 / 429 returned to client])

    B -->|Yes| C{vLLM GPU\nhealthy?}

    C -->|Yes| D[Route → vLLM\nQwen3-4B-Instruct]
    C -->|"No — retry × 3\n(exponential backoff)"| E{Ollama on host\nhealthy?\nhost.docker.internal:11434}

    E -->|Yes| F[Route → Ollama\ntinyllama]
    E -->|No| G{OPENAI_API_KEY\nset in .env?}

    G -->|Yes| H[Route → OpenAI\ngpt-4o-mini]
    G -->|No| Z2([503 All backends unavailable])

    D --> OUT([Stream response to client\nlog usage → PostgreSQL\ncache → Redis\nmetrics → Prometheus])
    F --> OUT
    H --> OUT

    style A fill:#2ecc71,color:#fff
    style OUT fill:#3498db,color:#fff
    style Z1 fill:#e74c3c,color:#fff
    style Z2 fill:#e74c3c,color:#fff
    style D fill:#27ae60,color:#fff
    style F fill:#f39c12,color:#fff
    style H fill:#8e44ad,color:#fff
```

## Fallback Configuration (`litellm/config.yaml`)

```yaml
router_settings:
  routing_strategy: least-busy
  num_retries: 3

fallbacks:
  - {"qwen3-4b": ["tinyllama"]}     # GPU down → local Ollama
  - {"tinyllama": ["gpt-4o-mini"]}  # Ollama down → OpenAI cloud
```
