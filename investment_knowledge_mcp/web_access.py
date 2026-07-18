from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hmac


class AccessClass(str, Enum):
    PUBLIC_READ = "public_read"
    PROTECTED = "protected"
    PUBLIC_READ_PROTECTED_WRITE = "public_read_protected_write"


@dataclass(frozen=True)
class BrowserAccessConfig:
    token: str | None = field(repr=False)
    source: str | None
    conflict: bool = False

    @classmethod
    def resolve(
        cls,
        canonical: str | None,
        command_legacy: str | None,
        weekly_legacy: str | None,
    ) -> BrowserAccessConfig:
        values = {
            "APP_ACCESS_TOKEN": _clean_token(canonical),
            "COMMAND_API_TOKEN": _clean_token(command_legacy),
            "WEEKLY_REVIEW_WEB_TOKEN": _clean_token(weekly_legacy),
        }
        configured = {key: value for key, value in values.items() if value is not None}
        if not configured:
            return cls(token=None, source=None)
        if len(set(configured.values())) != 1:
            return cls(token=None, source=None, conflict=True)
        token = next(iter(configured.values()))
        source = "APP_ACCESS_TOKEN" if values["APP_ACCESS_TOKEN"] else "legacy"
        return cls(token=token, source=source)


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    error_code: str | None = None


def extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return _clean_token(authorization.removeprefix("Bearer "))


def authorize_request(
    access_class: AccessClass,
    *,
    method: str,
    configured: BrowserAccessConfig,
    supplied_tokens: tuple[str | None, ...],
) -> AccessDecision:
    normalized_method = method.strip().upper()
    if access_class is AccessClass.PUBLIC_READ:
        return AccessDecision(allowed=True)
    if (
        access_class is AccessClass.PUBLIC_READ_PROTECTED_WRITE
        and normalized_method in {"GET", "HEAD", "OPTIONS"}
    ):
        return AccessDecision(allowed=True)
    if configured.conflict or configured.token is None:
        return AccessDecision(allowed=False, error_code="access_not_configured")
    candidates = tuple(
        candidate
        for supplied in supplied_tokens
        if (candidate := _clean_token(supplied)) is not None
    )
    if not candidates:
        return AccessDecision(allowed=False, error_code="access_required")
    if any(hmac.compare_digest(candidate, configured.token) for candidate in candidates):
        return AccessDecision(allowed=True)
    return AccessDecision(allowed=False, error_code="access_rejected")


def _clean_token(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None
