"""
MLflow Model Registry — config-catalog pattern for vLLM serving variants.

This module tracks *serving configurations* (base model + quantization +
adapter), not loadable weights. vLLM owns the weights; MLflow owns the
provenance record. mlflow.pyfunc.load_model() on a registered version will
fail — that is expected and by design.

Usage:
    uv run llmops-register

Required env:
    MLFLOW_REGISTER_MODEL — registered model name (e.g. "qwen3-4b-awq")

Optional env:
    MODEL_QUANTIZATION — quantization variant (e.g. "awq", "gptq", "fp16")
    MODEL_ADAPTER      — LoRA adapter path or HF hub name
    MODEL_ALIAS        — alias to set on the new version (e.g. "champion")
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import mlflow
from mlflow import MlflowClient
from mlflow.exceptions import MlflowException


def _serving_config() -> dict[str, str]:
    config: dict[str, str] = {
        "model": os.environ["VLLM_MODEL"],
        "api_base": os.environ["VLLM_API_BASE"],
    }
    if q := os.environ.get("MODEL_QUANTIZATION", ""):
        config["quantization"] = q
    if a := os.environ.get("MODEL_ADAPTER", ""):
        config["adapter"] = a
    return config


def _get_or_create(client: MlflowClient, name: str) -> None:
    try:
        client.get_registered_model(name)
    except MlflowException:
        client.create_registered_model(
            name=name,
            description=(
                "vLLM serving configuration catalog. "
                "Each version records a base-model + quantization + adapter combination. "
                "Not loadable via pyfunc — weights are managed by vLLM."
            ),
        )


def set_alias(model_name: str, alias: str, version: int) -> None:
    """Promote a version by setting a named alias (e.g. 'champion', 'challenger')."""
    MlflowClient().set_registered_model_alias(model_name, alias, str(version))


def register() -> None:
    """Entry point for `uv run llmops-register`.

    Creates a dedicated MLflow run, logs the serving config as an artifact,
    registers a model version, and optionally sets an alias.
    """
    from dotenv import load_dotenv

    load_dotenv()

    model_name = os.environ["MLFLOW_REGISTER_MODEL"]
    config = _serving_config()

    mlflow.set_tracking_uri(
        os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")
    )
    mlflow.set_experiment(os.environ.get("MLFLOW_EXPERIMENT", "vllmops") + "-registry")

    client = MlflowClient()
    _get_or_create(client, model_name)

    with mlflow.start_run(run_name=model_name) as run:
        mlflow.set_tags(
            {
                "mlflow.user": os.environ["RUN_USER"],
                "user.email": os.environ["RUN_EMAIL"],
                "registration.model": model_name,
                **{f"config.{k}": v for k, v in config.items()},
            }
        )

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "serving_config.json"
            p.write_text(json.dumps(config, indent=2))
            mlflow.log_artifact(str(p), artifact_path="model")

        version_obj = client.create_model_version(
            name=model_name,
            source=f"runs:/{run.info.run_id}/model",
            run_id=run.info.run_id,
            description=json.dumps(config),
            await_creation_for=60,
        )
        version = int(version_obj.version)
        mlflow.set_tag("registered_version", str(version))

        alias = os.environ.get("MODEL_ALIAS", "")
        if alias:
            client.set_registered_model_alias(model_name, alias, str(version))
            mlflow.set_tag("registered_alias", alias)

    suffix = f" [{alias}]" if alias else ""
    print(f"Registered {model_name} v{version}{suffix}")
    print(f"  config: {json.dumps(config)}")
