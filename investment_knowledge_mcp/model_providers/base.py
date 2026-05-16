from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class EnrichmentRequest:
    draft: dict
    prompt: str


class ModelProvider(ABC):
    @abstractmethod
    def enrich_research_draft(self, request: EnrichmentRequest) -> dict:
        """Return an enriched research draft JSON object."""

