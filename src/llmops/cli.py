import importlib.metadata
import os
import time
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv()

import mlflow
from langchain_core.messages import HumanMessage
from mlflow.openai import autolog as openai_autolog

from llmops import cost, prompts
from llmops.client import build_llm


def _build_run_tags(correlation_id: str) -> dict[str, str]:
    tags: dict[str, str] = {
        "mlflow.user": os.environ["RUN_USER"],
        "user.email": os.environ["RUN_EMAIL"],
        "env": os.environ.get("APP_ENV", "dev"),
        "app.version": importlib.metadata.version("llmops"),
        "run.correlation_id": correlation_id,
    }
    if commit := os.environ.get("GIT_COMMIT", ""):
        tags["git.commit"] = commit
    return tags


def main() -> None:
    mlflow.set_experiment(os.environ.get("MLFLOW_EXPERIMENT", "vllmops"))
    openai_autolog()

    template_name = os.environ.get("PROMPT_TEMPLATE", "default")
    variables = prompts.collect_vars()
    prompt = prompts.render(template_name, variables)

    correlation_id = str(uuid4())
    llm = build_llm(extra_headers={"X-Correlation-ID": correlation_id})

    with mlflow.start_run():
        mlflow.set_tags(_build_run_tags(correlation_id))
        mlflow.log_params(
            {
                "model": os.environ["VLLM_MODEL"],
                "api_base": os.environ["VLLM_API_BASE"],
                "prompt_template": template_name,
                "prompt_chars": len(prompt),
                **{f"prompt_var.{k}": v for k, v in variables.items()},
            }
        )
        prompts.log_artifacts(template_name, prompt, variables)

        t0 = time.monotonic()
        output_chars = 0
        prompt_tokens = 0
        completion_tokens = 0
        for chunk in llm.stream([HumanMessage(content=prompt)]):
            print(chunk.content, end="", flush=True)
            output_chars += len(chunk.content)
            if meta := chunk.usage_metadata:
                prompt_tokens = meta.get("input_tokens") or prompt_tokens
                completion_tokens = meta.get("output_tokens") or completion_tokens
        print()

        latency_ms = (time.monotonic() - t0) * 1000
        mlflow.log_metrics(
            {
                "latency_ms": latency_ms,
                "output_chars": output_chars,
                "prompt_tokens": float(prompt_tokens),
                "completion_tokens": float(completion_tokens),
                "cost_usd": cost.compute_cost(prompt_tokens, completion_tokens),
            }
        )
