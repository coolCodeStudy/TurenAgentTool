from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Any
from urllib.parse import quote_plus

import httpx

from investment_knowledge_mcp.config import get_config


MAX_TEXT_CHARS = 3500


def send_text_message(content: str) -> dict[str, Any]:
    config = get_config()
    if not config.dingtalk_send_webhook:
        raise RuntimeError("DINGTALK_SEND_WEBHOOK is required")

    webhook = signed_webhook_url(
        webhook=config.dingtalk_send_webhook,
        secret=config.dingtalk_send_secret,
    )
    payload = {
        "msgtype": "text",
        "text": {
            "content": _truncate(content),
        },
    }
    with httpx.Client(timeout=30) as client:
        response = client.post(webhook, json=payload)
        response.raise_for_status()

    try:
        result = response.json()
    except ValueError as exc:
        body = response.text.strip()[:500]
        raise RuntimeError(
            f"DingTalk response was not JSON: status={response.status_code}, body={body!r}"
        ) from exc
    if not isinstance(result, dict):
        raise RuntimeError(f"unexpected DingTalk response: {result!r}")
    if result.get("errcode") not in (0, None):
        raise RuntimeError(f"DingTalk send failed: {result}")
    return result


def signed_webhook_url(webhook: str, secret: str | None, timestamp_ms: int | None = None) -> str:
    if not secret:
        return webhook

    timestamp = str(timestamp_ms or int(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), string_to_sign, hashlib.sha256).digest()
    sign = quote_plus(base64.b64encode(digest).decode("utf-8"))
    separator = "&" if "?" in webhook else "?"
    return f"{webhook}{separator}timestamp={timestamp}&sign={sign}"


def _truncate(content: str) -> str:
    if len(content) <= MAX_TEXT_CHARS:
        return content
    return content[:MAX_TEXT_CHARS] + "\n\n...内容过长，已截断。"
