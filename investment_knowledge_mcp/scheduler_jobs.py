from __future__ import annotations

from collections.abc import Callable, Sequence
from time import monotonic

from investment_knowledge_mcp.scheduler_host import JobDefinition, JobExecutor, SchedulerHost


def build_scheduler_host(
    jobs: Sequence[JobDefinition],
    *,
    clock: Callable[[], float] = monotonic,
    executor: JobExecutor | None = None,
) -> SchedulerHost:
    """Composition boundary for job adapters registered by later migrations."""

    return SchedulerHost(jobs, clock=clock, executor=executor)
