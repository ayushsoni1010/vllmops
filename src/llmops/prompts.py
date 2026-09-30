import json
import os
from pathlib import Path

import jinja2


def _prompts_dir() -> Path:
    if override := os.environ.get("PROMPTS_DIR"):
        return Path(override)
    return Path.cwd() / "prompts"


def collect_vars() -> dict[str, str]:
    prefix = "PROMPT_VAR_"
    return {
        k[len(prefix) :].lower(): v
        for k, v in os.environ.items()
        if k.startswith(prefix)
    }


def render(name: str, variables: dict[str, str]) -> str:
    loader = jinja2.FileSystemLoader(str(_prompts_dir()))
    env = jinja2.Environment(
        loader=loader, undefined=jinja2.StrictUndefined, autoescape=False
    )
    return env.get_template(f"{name}.j2").render(**variables)


def log_artifacts(name: str, rendered: str, variables: dict[str, str]) -> None:
    import tempfile

    import mlflow

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "rendered.txt").write_text(rendered)
        (tmp_path / "variables.json").write_text(json.dumps(variables, indent=2))
        mlflow.log_artifacts(str(tmp_path), artifact_path="prompts")
    mlflow.log_artifact(str(_prompts_dir() / f"{name}.j2"), artifact_path="prompts")
