import importlib.metadata
import os
import time
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv()

import mlflow
from langchain_core.messages import HumanMessage
from mlflow.openai import autolog as openai_autolog

from llmops.client import build_llm


def _build_run_tags(correlation_id: str) -> dict[str, str]:
    tags: dict[str, str] = {
        # Identity — required; missing env vars crash loudly per project convention.
        "mlflow.user": os.environ["RUN_USER"],
        "user.email": os.environ["RUN_EMAIL"],
        # Deployment context — optional, safe defaults for local dev.
        "env": os.environ.get("APP_ENV", "dev"),
        # Package version — ties run to an exact release without needing git.
        "app.version": importlib.metadata.version("llmops"),
        # Correlation ID — joins this run to LiteLLM/nginx request logs.
        "run.correlation_id": correlation_id,
    }
    # Sparse tags: only present when the value is set (typically by CI/CD).
    if commit := os.environ.get("GIT_COMMIT", ""):
        tags["git.commit"] = commit
    return tags


def main() -> None:
    mlflow.set_experiment(os.environ.get("MLFLOW_EXPERIMENT", "vllmops"))
    openai_autolog()

    correlation_id = str(uuid4())
    llm = build_llm(extra_headers={"X-Correlation-ID": correlation_id})
    prompt = os.environ["PROMPT"]

    with mlflow.start_run():
        mlflow.set_tags(_build_run_tags(correlation_id))
        mlflow.log_params({
            "model": os.environ["VLLM_MODEL"],
            "api_base": os.environ["VLLM_API_BASE"],
            "prompt_chars": len(prompt),
        })

        t0 = time.monotonic()
        output_chars = 0
        for chunk in llm.stream([HumanMessage(content=prompt)]):
            print(chunk.content, end="", flush=True)
            output_chars += len(chunk.content)
        print()

        mlflow.log_metrics({
            "latency_ms": (time.monotonic() - t0) * 1000,
            "output_chars": output_chars,
        })
