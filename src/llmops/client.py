import os

from langchain_openai import ChatOpenAI
from pydantic import SecretStr


def build_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=os.environ["VLLM_MODEL"],
        base_url=os.environ["VLLM_API_BASE"],
        api_key=SecretStr(os.environ["VLLM_API_KEY"]),
    )
