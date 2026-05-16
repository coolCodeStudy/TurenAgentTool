from __future__ import annotations

from investment_knowledge_mcp.model_providers.base import ModelProvider
from investment_knowledge_mcp.model_providers.mock import MockModelProvider
from investment_knowledge_mcp.model_providers.openai_provider import OpenAIModelProvider


def create_model_provider(name: str) -> ModelProvider:
    if name == "mock":
        return MockModelProvider()
    if name == "openai":
        return OpenAIModelProvider()
    raise ValueError("provider must be one of: mock, openai")

