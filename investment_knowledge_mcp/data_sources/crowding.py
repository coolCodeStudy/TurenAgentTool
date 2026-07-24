"""Approved source metadata and adapters for crowded-trade evidence."""

from __future__ import annotations

from dataclasses import dataclass


def _normalized(value: str, field: str) -> str:
    if not isinstance(value, str) or not (cleaned := value.strip().casefold()):
        raise ValueError(f"{field} must be non-empty")
    return cleaned


def _normalized_tuple(values: tuple[str, ...], field: str, *, upper: bool = False) -> tuple[str, ...]:
    normalized = tuple(
        _normalized(value, field).upper() if upper else _normalized(value, field)
        for value in values
    )
    if not normalized:
        raise ValueError(f"{field} must be non-empty")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field} must not contain duplicates")
    return normalized


@dataclass(frozen=True)
class SourceApproval:
    source_id: str
    access_tier: str
    permitted_uses: tuple[str, ...]
    redistribution_allowed: bool
    enabled_markets: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _normalized(self.source_id, "source_id"))
        object.__setattr__(self, "access_tier", _normalized(self.access_tier, "access_tier"))
        object.__setattr__(
            self,
            "permitted_uses",
            _normalized_tuple(tuple(self.permitted_uses), "permitted_uses"),
        )
        object.__setattr__(
            self,
            "enabled_markets",
            _normalized_tuple(tuple(self.enabled_markets), "enabled_markets", upper=True),
        )
        if not isinstance(self.redistribution_allowed, bool):
            raise ValueError("redistribution_allowed must be a boolean")


FUTU_CROWDING_APPROVAL = SourceApproval(
    source_id="futu_crowding",
    access_tier="account_entitled",
    permitted_uses=("private_internal_research",),
    redistribution_allowed=False,
    enabled_markets=("US", "HK"),
)

SOURCE_APPROVALS = {
    FUTU_CROWDING_APPROVAL.source_id: FUTU_CROWDING_APPROVAL,
}


def source_is_approved(source_id: str, use_case: str) -> bool:
    try:
        normalized_source = _normalized(source_id, "source_id")
        normalized_use = _normalized(use_case, "use_case")
    except ValueError:
        return False
    approval = SOURCE_APPROVALS.get(normalized_source)
    return approval is not None and normalized_use in approval.permitted_uses
