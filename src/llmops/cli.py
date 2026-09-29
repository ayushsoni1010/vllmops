import os

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from mlflow.langchain import autolog as langchain_autolog

from llmops.client import build_llm


def main() -> None:
    load_dotenv()
    langchain_autolog()

    llm = build_llm()
    prompt = os.environ["PROMPT"]

    for chunk in llm.stream([HumanMessage(content=prompt)]):
        print(chunk.content, end="", flush=True)
    print()
