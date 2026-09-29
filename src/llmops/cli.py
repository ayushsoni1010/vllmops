import os

import mlflow
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

from llmops.client import build_llm


def main() -> None:
    load_dotenv()
    llm = build_llm()
    prompt = os.environ["PROMPT"]

    with mlflow.start_run():
        mlflow.log_params({
            "model": os.environ["VLLM_MODEL"],
            "api_base": os.environ["VLLM_API_BASE"],
            "prompt_chars": len(prompt),
        })
        for chunk in llm.stream([HumanMessage(content=prompt)]):
            print(chunk.content, end="", flush=True)
        print()
