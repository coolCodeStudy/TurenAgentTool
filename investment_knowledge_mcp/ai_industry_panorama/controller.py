from __future__ import annotations

from http import HTTPStatus
from typing import Any
from urllib.parse import ParseResult

from investment_knowledge_mcp.ai_industry_panorama.release import (
    PanoramaReleaseError,
    build_public_projection,
    load_release,
)
from investment_knowledge_mcp.ai_industry_panorama.web import (
    render_panorama_html,
    render_panorama_script,
)


def dispatch_panorama_get(handler: Any, parsed: ParseResult) -> bool:
    if parsed.path == "/ai-industry-panorama":
        handler._write_html(HTTPStatus.OK, render_panorama_html())
        return True
    if parsed.path == "/assets/ai-industry-panorama.js":
        handler._write_javascript(HTTPStatus.OK, render_panorama_script())
        return True
    if parsed.path != "/api/ai-industry-panorama":
        return False

    try:
        projection = build_public_projection(load_release())
    except PanoramaReleaseError:
        handler._write_json(
            HTTPStatus.SERVICE_UNAVAILABLE,
            {
                "ok": False,
                "error": "panorama_unavailable",
                "message": "AI Industry Panorama data is temporarily unavailable.",
            },
        )
        return True

    handler._write_json(HTTPStatus.OK, projection)
    return True
