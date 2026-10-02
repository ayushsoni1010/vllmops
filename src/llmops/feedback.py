"""
Human feedback collection for DPO/RLHF dataset construction.

Each labelled run in the vllmops experiment is a training record:
    prompt  → prompts/rendered.txt artifact
    response → MLflow trace (openai_autolog)
    label   → feedback metric (1.0 = good, 0.0 = bad)

Query labelled runs for export:
    mlflow.search_runs(
        experiment_names=["vllmops"],
        filter_string="metrics.feedback >= 0",
    )
"""

import os
import sys

import mlflow

_SCORES: dict[str, float] = {"good": 1.0, "bad": 0.0}


def collect() -> None:
    """Log human feedback to the active MLflow run.

    Priority order:
    1. FEEDBACK env var set to 'good' or 'bad' — logs without prompting.
    2. Interactive TTY — prompts the user after the response; Enter/s skips.
    3. Non-TTY stdin (piped output, CI) — silent no-op unless FEEDBACK is set.
    """
    label = os.environ.get("FEEDBACK", "").strip().lower()

    if not label:
        if not sys.stdin.isatty():
            return
        try:
            sys.stdout.write("\nFeedback [g=good  b=bad  Enter=skip]: ")
            sys.stdout.flush()
            raw = sys.stdin.readline().strip().lower()
            if raw in ("g", "good"):
                label = "good"
            elif raw in ("b", "bad"):
                label = "bad"
        except (EOFError, KeyboardInterrupt):
            return

    if label in _SCORES:
        mlflow.log_metric("feedback", _SCORES[label])
        mlflow.set_tag("feedback_label", label)
