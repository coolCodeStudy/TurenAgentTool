from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

from investment_knowledge_mcp.model_providers.base import EnrichmentRequest, ModelProvider


RESPONSES_API_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5.2"


class OpenAIModelProvider(ModelProvider):
    """OpenAI Responses API provider for research draft enrichment."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float = 120,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
        self.timeout_seconds = timeout_seconds

    def enrich_research_draft(self, request: EnrichmentRequest) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required when using --provider openai")

        payload = {
            "model": self.model,
            "input": [
                {
                    "role": "user",
                    "content": request.prompt,
                }
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "research_draft",
                    "schema": research_draft_json_schema(),
                    "strict": False,
                }
            },
        }

        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(
                RESPONSES_API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()

        output_text = extract_response_text(response.json())
        return parse_json_output(output_text)


def extract_response_text(response_payload: dict[str, Any]) -> str:
    if isinstance(response_payload.get("output_text"), str):
        return response_payload["output_text"]

    parts: list[str] = []
    for output_item in response_payload.get("output", []):
        if not isinstance(output_item, dict):
            continue
        for content_item in output_item.get("content", []):
            if not isinstance(content_item, dict):
                continue
            if isinstance(content_item.get("text"), str):
                parts.append(content_item["text"])

    if not parts:
        raise ValueError("OpenAI response did not contain output text")
    return "\n".join(parts)


def parse_json_output(output_text: str) -> dict[str, Any]:
    text = output_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("OpenAI enriched draft output must be a JSON object")
    return payload


def research_draft_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": True,
        "required": ["stock", "sources", "sectors", "knowledge_items", "user_insights"],
        "properties": {
            "stock": {
                "type": "object",
                "additionalProperties": True,
                "required": ["symbol", "market"],
                "properties": {
                    "symbol": {"type": "string"},
                    "market": {"type": "string"},
                    "name": {"type": "string"},
                    "core_business": {"type": "string"},
                    "equity_structure": {"type": "string"},
                    "stock_character": {"type": "string"},
                    "notable_history": {"type": "string"},
                },
            },
            "sources": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": True,
                    "required": ["key", "source_type", "title"],
                    "properties": {
                        "key": {"type": "string"},
                        "source_type": {"type": "string"},
                        "title": {"type": "string"},
                        "url": {"type": "string"},
                        "publisher": {"type": "string"},
                        "published_at": {"type": "string"},
                        "notes": {"type": "string"},
                        "content_excerpt": {"type": "string"},
                    },
                },
            },
            "sectors": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": True,
                    "required": ["path", "relation_type", "confidence"],
                    "properties": {
                        "path": {"type": "array", "items": {"type": "string"}},
                        "relation_type": {"type": "string"},
                        "confidence": {"type": "number"},
                        "source_key": {"type": "string"},
                        "description": {"type": "string"},
                        "recent_status": {"type": "string"},
                    },
                },
            },
            "knowledge_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": True,
                    "required": ["knowledge_type", "content", "confidence", "source_key"],
                    "properties": {
                        "knowledge_type": {"type": "string"},
                        "content": {"type": "string"},
                        "confidence": {"type": "number"},
                        "source_key": {"type": "string"},
                        "stale_after": {"type": "string"},
                    },
                },
            },
            "user_insights": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": True,
                    "required": ["insight"],
                    "properties": {
                        "insight": {"type": "string"},
                        "normalized_summary": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
        },
    }
