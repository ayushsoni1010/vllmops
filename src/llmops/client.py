import os

from langchain_ollama import ChatOllama


def build_llm() -> ChatOllama:
    return ChatOllama(
        model=os.environ["OLLAMA_MODEL"],
        base_url=os.environ["OLLAMA_HOST"],
    )
