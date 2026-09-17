import os

import mlflow
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

from llmops.client import build_llm


def main() -> None:
    load_dotenv()
    mlflow.langchain.autolog()

    llm = build_llm()
    prompt = os.environ["PROMPT"]

    for chunk in llm.stream([HumanMessage(content=prompt)]):
        print(chunk.content, end="", flush=True)
    print()
