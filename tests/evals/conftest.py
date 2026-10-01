import os

import mlflow
import pytest
from dotenv import load_dotenv

load_dotenv()

from llmops.client import build_llm


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "eval: LLM evaluation tests — require the live stack; run with `uv run pytest tests/evals/`",
    )


@pytest.fixture(scope="session")
def llm():
    return build_llm()


@pytest.fixture(scope="session", autouse=True)
def eval_experiment():
    mlflow.set_experiment(os.environ.get("MLFLOW_EXPERIMENT", "vllmops") + "-evals")
    yield
