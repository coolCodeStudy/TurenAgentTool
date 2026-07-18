"""Provider-neutral admission for Daily Market activity transports.

The transports still own their request signatures, deadlines, and host gates.
This module owns the normalized source result and the section fallback contract;
the Daily Market feature remains responsible for deciding which evidence is fit
for narrative and persistence.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime, timezone
from typing import Any

from .contracts import (
    DataRequest,
    DataResult,
    DataStatus,
    ProviderDescriptor,
    ProviderFailure,
    SourceCapability,
    SourcePlan,
)
from .pool import DataSourcePool, ResultCache


ACTIVITY_SECTIONS = ("sectors", "gainers", "capital_flow")
ACTIVITY_MARKETS = ("CN", "HK", "US")
_COVERED_STATUSES = frozenset({"ok", "partial", "timed_out"})
_RETRYABLE_STATUSES = frozenset({"provider_unavailable", "timed_out"})


class ActivityFallbackRows(list[dict[str, Any]]):
    """Rows carrying safe nested-transport provenance between adapter layers."""

    def __init__(
        self,
        rows: Sequence[Mapping[str, Any]],
        *,
        selected_provider: str,
        fallback_chain: tuple[str, ...],
        fallback_reasons: tuple[str, ...],
    ) -> None:
        super().__init__(dict(row) for row in rows)
        self.selected_provider = selected_provider
        self.fallback_chain = fallback_chain
        self.fallback_reasons = fallback_reasons


class MarketActivitySource:
    """Adapt one legacy activity transport into the shared data-source contract."""

    def __init__(
        self,
        source_id: str,
        loader: Callable[[str, date], object],
        *,
        cancellation_exceptions: tuple[type[BaseException], ...] = (),
        timeout_seconds: float = 90.0,
    ) -> None:
        self.descriptor = ProviderDescriptor(
            source_id,
            (SourceCapability.MARKET_ACTIVITY,),
            ACTIVITY_MARKETS,
            timeout_seconds,
            0,
            "market_activity",
            0,
        )
        self._loader = loader
        self._cancellation_exceptions = cancellation_exceptions

    def fetch(self, request: DataRequest) -> DataResult:
        source_id = self.descriptor.source_id
        fetched_at = datetime.now(timezone.utc)
        if not _valid_request(request):
            return _unavailable(source_id, "invalid_request", fetched_at, fallback_allowed=False)

        try:
            payload = self._loader(request.market, request.start)
        except self._cancellation_exceptions:
            return _unavailable(source_id, "cancelled", fetched_at, fallback_allowed=False)
        except Exception as exc:
            return _unavailable(
                source_id,
                "provider_unavailable",
                fetched_at,
                retryable=True,
                detail=type(exc).__name__,
            )

        if hasattr(payload, "as_dict"):
            payload = payload.as_dict()
        try:
            records, failures, coverage, unavailable = _normalize_payload(payload, source_id)
        except (TypeError, ValueError):
            return _unavailable(source_id, "provider_contract_error", fetched_at)

        if unavailable:
            return DataResult(
                DataStatus.UNAVAILABLE,
                records,
                None,
                (source_id,),
                coverage,
                fetched_at,
                False,
                failures,
            )
        status = DataStatus.OK if not failures and coverage == 1.0 else DataStatus.PARTIAL
        return DataResult(
            status,
            records,
            source_id,
            (source_id,),
            coverage,
            fetched_at,
            False,
            failures,
        )


def default_market_activity_pool(
    source: MarketActivitySource,
    *,
    cache: ResultCache | None = None,
) -> DataSourcePool:
    """Create an in-process pool containing an explicitly configured adapter."""
    pool = DataSourcePool(cache=cache)
    pool.register(source)
    return pool


def market_activity_plan(source_id: str) -> SourcePlan:
    """Return the one-capability plan used by the Daily Market feature."""
    return SourcePlan(
        capability=SourceCapability.MARKET_ACTIVITY,
        preferred_sources=(source_id,),
        allowed_sources=(source_id,),
        fallback_sources=(),
        required=False,
        partial_allowed=True,
    )


def market_activity_sections(result: DataResult) -> dict[str, dict[str, Any]]:
    """Mechanically decode normalized records; make no product admission decision."""
    decoded: dict[str, dict[str, Any]] = {}
    for record in result.records:
        if not isinstance(record, Mapping):
            raise ValueError("market activity record must be a mapping")
        section = record.get("section")
        rows = record.get("rows")
        source_status = record.get("source_status")
        if section not in ACTIVITY_SECTIONS or section in decoded:
            raise ValueError("market activity record has an invalid section")
        if not isinstance(rows, tuple) or any(not isinstance(row, Mapping) for row in rows):
            raise ValueError("market activity rows must be mappings in a tuple")
        if not isinstance(source_status, Mapping):
            raise ValueError("market activity source status must be a mapping")
        decoded[str(section)] = {
            "rows": [dict(row) for row in rows],
            "source_status": dict(source_status),
            "covered": bool(record.get("covered")),
        }
    if decoded and set(decoded) != set(ACTIVITY_SECTIONS):
        raise ValueError("market activity result must contain every section")
    return decoded


def load_activity_section(
    *,
    provider: str,
    section: str,
    fallback_message: str,
    loader: Callable[[], list[dict[str, Any]]],
    fallback_provider: str | None = None,
    fallback_loader: Callable[[], list[dict[str, Any]]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Execute a section transport and its admitted fallback with safe provenance."""
    if section not in ACTIVITY_SECTIONS:
        raise ValueError(f"unknown market activity section: {section}")
    primary_provider = provider
    detail_code = ""
    used_fallback = False
    nested_chain: tuple[str, ...] = ()
    nested_reasons: tuple[str, ...] = ()
    try:
        rows = loader()
    except Exception as exc:
        rows = []
        detail_code = type(exc).__name__
    if not rows and fallback_loader is not None and fallback_provider is not None:
        used_fallback = True
        try:
            rows = fallback_loader()
        except Exception as exc:
            return [], {
                "status": "provider_unavailable",
                "provider": f"{provider},{fallback_provider}",
                "count": 0,
                "message": fallback_message,
                "detail_code": ",".join(
                    part for part in (detail_code, type(exc).__name__) if part
                ),
            }
        if rows:
            provider = str(getattr(rows, "selected_provider", "") or fallback_provider)
            nested_chain = tuple(getattr(rows, "fallback_chain", ()))
            nested_reasons = tuple(getattr(rows, "fallback_reasons", ()))
    status = "ok" if rows else "missing"
    result: dict[str, Any] = {
        "status": status,
        "provider": provider,
        "count": len(rows),
    }
    if section == "sectors":
        result["taxonomy"] = "provider_native"
    if used_fallback and provider != primary_provider:
        result["fallback_from"] = primary_provider
        result["fallback_reason"] = detail_code or "empty_result"
    if nested_chain:
        result["fallback_chain"] = (primary_provider, *nested_chain)
        result["fallback_reasons"] = (
            detail_code or "empty_result",
            *nested_reasons,
        )
    if not rows:
        result["message"] = fallback_message
    return rows, result


def _valid_request(request: DataRequest) -> bool:
    return (
        request.capability is SourceCapability.MARKET_ACTIVITY
        and request.start is not None
        and request.end == request.start
        and not request.symbols
    )


def _normalize_payload(
    payload: object,
    source_id: str,
) -> tuple[tuple[dict[str, Any], ...], tuple[ProviderFailure, ...], float, bool]:
    if not isinstance(payload, Mapping):
        raise TypeError("activity payload must be a mapping")
    statuses = payload.get("source_status")
    if not isinstance(statuses, Mapping):
        raise TypeError("source_status must be a mapping")

    records: list[dict[str, Any]] = []
    failures: list[ProviderFailure] = []
    covered_count = 0
    unavailable_count = 0
    for section in ACTIVITY_SECTIONS:
        rows = payload.get(section)
        section_status = statuses.get(section)
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
            raise TypeError(f"{section} must be a sequence")
        if not isinstance(section_status, Mapping):
            raise TypeError(f"{section} status must be a mapping")
        copied_rows = tuple(_copy_row(row) for row in rows)
        copied_status = dict(section_status)
        status = copied_status.get("status")
        if not isinstance(status, str) or not status.strip():
            raise ValueError(f"{section} status must be non-empty")
        status = status.strip()
        covered = status in _COVERED_STATUSES and bool(copied_rows)
        if covered:
            covered_count += 1
        if status == "provider_unavailable":
            unavailable_count += 1
        if status != "ok":
            failures.append(
                ProviderFailure(
                    status,
                    source_id,
                    status in _RETRYABLE_STATUSES,
                    status in _RETRYABLE_STATUSES,
                    section,
                )
            )
        records.append(
            {
                "section": section,
                "rows": copied_rows,
                "source_status": copied_status,
                "covered": covered,
            }
        )
    return (
        tuple(records),
        tuple(failures),
        covered_count / len(ACTIVITY_SECTIONS),
        unavailable_count == len(ACTIVITY_SECTIONS),
    )


def _copy_row(row: object) -> dict[str, Any]:
    if not isinstance(row, Mapping):
        raise TypeError("activity row must be a mapping")
    return dict(row)


def _unavailable(
    source_id: str,
    code: str,
    fetched_at: datetime,
    *,
    retryable: bool = False,
    fallback_allowed: bool = True,
    detail: str | None = None,
) -> DataResult:
    return DataResult(
        DataStatus.UNAVAILABLE,
        (),
        None,
        (source_id,),
        0.0,
        fetched_at,
        False,
        (ProviderFailure(code, source_id, retryable, fallback_allowed, detail),),
    )
