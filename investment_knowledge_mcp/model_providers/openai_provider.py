from __future__ import annotations

from investment_knowledge_mcp.model_providers.base import EnrichmentRequest, ModelProvider


class OpenAIModelProvider(ModelProvider):
    """Placeholder for the real OpenAI-backed provider."""

    def enrich_research_draft(self, request: EnrichmentRequest) -> dict:
        raise NotImplementedError(
            "OpenAI provider is not wired yet. Use --provider mock for workflow testing."
        )

