import os


def compute_cost(prompt_tokens: int, completion_tokens: int) -> float:
    prompt_rate = float(os.environ.get("PROMPT_TOKEN_COST", "0.0"))
    completion_rate = float(os.environ.get("COMPLETION_TOKEN_COST", "0.0"))
    return prompt_tokens * prompt_rate + completion_tokens * completion_rate
