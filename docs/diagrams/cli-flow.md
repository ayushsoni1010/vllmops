# CLI Flow — `uv run llmops`

How the Python CLI processes a prompt and records the trace.

```mermaid
sequenceDiagram
    autonumber
    participant U  as User (terminal)
    participant E  as .env file
    participant C  as cli.py (main)
    participant B  as client.py (build_llm)
    participant ML as MLflow Server<br/>localhost:5000
    participant L  as LiteLLM Gateway<br/>localhost:4000
    participant V  as vLLM / Ollama

    U  ->> C  : uv run llmops
    C  ->> E  : load_dotenv() — reads OLLAMA_HOST, OLLAMA_MODEL, PROMPT, …
    C  ->> ML : mlflow.langchain.autolog() — patches LangChain to record traces

    C  ->> B  : build_llm()
    B  -->> C : ChatOllama(model=OLLAMA_MODEL, base_url=OLLAMA_HOST)
    note over B,C : For full stack: ChatOpenAI(base_url=VLLM_API_BASE)<br/>swap by changing client.py + .env

    C  ->> L  : llm.stream([HumanMessage(PROMPT)])
    L  ->> V  : forward to configured backend

    loop Token streaming
        V  -->> L  : token chunk
        L  -->> C  : token chunk
        C  -->> U  : print(chunk.content, end="", flush=True)
    end

    V  -->> L  : [DONE]
    L  -->> C  : stream exhausted
    C  -->> U  : print("\\n")

    C  ->> ML : autolog flushes run: inputs, outputs, latency, model params
    note over U,ML : Trace visible at http://localhost:5000
```

## Local dev vs. full stack

| Mode | `build_llm()` returns | Backend hit |
|---|---|---|
| `uv run llmops` (local) | `ChatOllama` | Ollama on host :11434 |
| `uv run llmops` (full stack) | `ChatOpenAI` pointing at LiteLLM | nginx → LiteLLM → vLLM |

Switch by editing `src/llmops/client.py` and the relevant `.env` vars.
