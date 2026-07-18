"""Deterministic in-process execution for provider-neutral data sources."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import replace
from datetime import datetime, timezone
from time import monotonic
from typing import Callable, Protocol

from .contracts import (
    DataRequest,
    DataResult,
    DataStatus,
    ProviderDescriptor,
    ProviderFailure,
    SourcePlan,
)


class ExternalDataSource(Protocol):
    descriptor: ProviderDescriptor

    def fetch(self, request: DataRequest) -> DataResult: ...


class ResultCache(Protocol):
    def get(self, request: DataRequest, source_id: str) -> DataResult | None: ...

    def put(self, request: DataRequest, source_id: str, result: DataResult, ttl_seconds: int) -> None: ...


class MemoryResultCache:
    """A bounded cache with monotonic expiry for normalized source results."""

    def __init__(self, max_entries: int = 128, *, clock: Callable[[], float] = monotonic) -> None:
        if not isinstance(max_entries, int) or isinstance(max_entries, bool) or max_entries <= 0:
            raise ValueError("max_entries must be a positive integer")
        self._max_entries = max_entries
        self._clock = clock
        self._entries: OrderedDict[tuple[DataRequest, str], tuple[float, DataResult]] = OrderedDict()

    def get(self, request: DataRequest, source_id: str) -> DataResult | None:
        key = (request, source_id.casefold())
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, result = entry
        if expires_at <= self._clock():
            del self._entries[key]
            return None
        self._entries.move_to_end(key)
        return replace(result, from_cache=True)

    def put(self, request: DataRequest, source_id: str, result: DataResult, ttl_seconds: int) -> None:
        if result.status not in (DataStatus.OK, DataStatus.PARTIAL):
            return
        key = (request, source_id.casefold())
        self._entries[key] = (self._clock() + ttl_seconds, replace(result, from_cache=False))
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)


class DataSourcePool:
    def __init__(
        self,
        *,
        cache: ResultCache | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._cache = cache
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._providers: dict[str, ExternalDataSource] = {}

    def register(self, provider: ExternalDataSource) -> None:
        descriptor = provider.descriptor
        source_id = descriptor.source_id
        if source_id in self._providers:
            raise ValueError(f"provider already registered: {source_id}")
        self._providers[source_id] = provider

    def fetch(self, request: DataRequest, plan: SourcePlan) -> DataResult:
        plan.validate_request(request)
        attempts: list[str] = []
        failures: list[ProviderFailure] = []
        candidates = _candidates(plan)

        for index, source_id in enumerate(candidates):
            attempts.append(source_id)
            provider = self._providers.get(source_id)
            if provider is None:
                failures.append(_failure("provider_not_registered", source_id, retryable=False, fallback_allowed=True))
                if self._may_advance(failures, candidates, index, plan):
                    continue
                break
            if request.capability not in provider.descriptor.capabilities or request.market not in provider.descriptor.markets:
                failures.append(_failure("provider_not_compatible", source_id, retryable=False, fallback_allowed=True))
                if self._may_advance(failures, candidates, index, plan):
                    continue
                break

            cached = self._cache.get(request, source_id) if self._cache is not None else None
            if cached is not None:
                return _combined(cached, attempts, failures)

            try:
                provider_result = provider.fetch(request)
            except Exception:
                failures.append(_failure("provider_exception", source_id, retryable=False, fallback_allowed=True))
                if self._may_advance(failures, candidates, index, plan):
                    continue
                break

            if not _valid_provider_result(provider_result, source_id):
                failures.append(_failure("provider_contract_error", source_id, retryable=False, fallback_allowed=True))
                if self._may_advance(failures, candidates, index, plan):
                    continue
                break

            attempts = list(_ordered_unique((*attempts, *provider_result.attempted_sources)))
            failures.extend(provider_result.failures)
            normalized = replace(provider_result, attempted_sources=(source_id,), failures=(), from_cache=False)
            if provider_result.status is DataStatus.OK:
                self._put_cached(request, source_id, normalized, provider.descriptor.default_ttl_seconds)
                return _combined(provider_result, attempts, failures)
            if provider_result.status is DataStatus.PARTIAL and plan.partial_allowed:
                self._put_cached(request, source_id, normalized, provider.descriptor.default_ttl_seconds)
                return _combined(provider_result, attempts, failures)
            if provider_result.status is DataStatus.PARTIAL:
                failures.append(_failure("partial_not_allowed", source_id, retryable=False, fallback_allowed=True))

            if self._may_advance(failures, candidates, index, plan):
                continue
            break

        return DataResult(DataStatus.UNAVAILABLE, (), None, tuple(attempts), 0.0, self._now(), False, tuple(failures))

    def _put_cached(self, request: DataRequest, source_id: str, result: DataResult, ttl_seconds: int) -> None:
        if self._cache is not None:
            self._cache.put(request, source_id, result, ttl_seconds)

    @staticmethod
    def _may_advance(
        failures: list[ProviderFailure], candidates: tuple[str, ...], index: int, plan: SourcePlan
    ) -> bool:
        return (
            index + 1 < len(candidates)
            and candidates[index + 1] in plan.fallback_sources
            and any(failure.fallback_allowed for failure in failures)
        )


def _candidates(plan: SourcePlan) -> tuple[str, ...]:
    return _ordered_unique((*plan.preferred_sources, *plan.fallback_sources))


def _ordered_unique(source_ids: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(source_ids))


def _failure(code: str, source_id: str, *, retryable: bool, fallback_allowed: bool) -> ProviderFailure:
    return ProviderFailure(code, source_id, retryable, fallback_allowed)


def _valid_provider_result(result: object, source_id: str) -> bool:
    return (
        isinstance(result, DataResult)
        and source_id in result.attempted_sources
        and (result.selected_source is None or result.selected_source == source_id)
    )


def _combined(result: DataResult, attempts: list[str] | tuple[str, ...], failures: list[ProviderFailure]) -> DataResult:
    return replace(
        result,
        attempted_sources=_ordered_unique(tuple(attempts)),
        failures=tuple(failures),
    )
