"""
Golden eval suite — pattern-based regression harness for the LLM stack.

Each case in fixtures/golden.yaml renders a prompt template, calls the model
via the LiteLLM gateway, checks output against expected_patterns, and logs
results to MLflow (experiment: <MLFLOW_EXPERIMENT>-evals).

Run:
    uv run pytest tests/evals/ -v

Note: mlflow.evaluate() is the right API for aggregate scoring with an
LLM-as-judge; these per-case pytest assertions cover the pattern-match layer.
Judge scoring will be added in tests/evals/judge.py once a judge model is wired.
"""

import re
import time
from pathlib import Path

import mlflow
import pytest
import yaml
from langchain_core.messages import HumanMessage

from llmops import prompts

_CASES = yaml.safe_load(
    (Path(__file__).parent / "fixtures" / "golden.yaml").read_text()
)["cases"]


@pytest.mark.eval
@pytest.mark.parametrize("case", _CASES, ids=[c["id"] for c in _CASES])
def test_golden(case, llm):
    variables = case.get("variables", {})
    prompt = prompts.render(case["template"], variables)

    with mlflow.start_run(run_name=case["id"]):
        mlflow.log_params(
            {
                "template": case["template"],
                **{f"var.{k}": v for k, v in variables.items()},
            }
        )

        t0 = time.monotonic()
        output = llm.invoke([HumanMessage(content=prompt)]).content
        latency_ms = (time.monotonic() - t0) * 1000

        mlflow.log_metrics({"latency_ms": latency_ms, "output_chars": len(output)})
        mlflow.log_text(output, "output.txt")
        prompts.log_artifacts(case["template"], prompt, variables)

        for pattern in case.get("expected_patterns", []):
            assert re.search(pattern, output), (
                f"Pattern not found: {pattern!r}\nOutput: {output[:300]}"
            )

        for pattern in case.get("not_expected_patterns", []):
            assert not re.search(pattern, output), (
                f"Forbidden pattern matched: {pattern!r}\nOutput: {output[:300]}"
            )

        if max_ms := case.get("max_latency_ms"):
            assert latency_ms < max_ms, (
                f"Latency {latency_ms:.0f}ms exceeded limit {max_ms}ms"
            )

        mlflow.log_metric("passed", 1.0)
