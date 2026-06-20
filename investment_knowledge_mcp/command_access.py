from __future__ import annotations

from typing import Any

from investment_knowledge_mcp.command_router import (
    is_candidate_write_command,
    is_coding_task_command,
    is_decision_write_command,
    is_maintenance_command,
    is_query_command,
    is_research_write_command,
)


WRITE_CATEGORIES = {
    "decision_write",
    "candidate_write",
    "research_write",
    "maintenance",
    "coding_task",
}


def classify_command(command: str) -> dict[str, Any]:
    cleaned = command.strip()
    if not cleaned:
        return _classification("unknown", "Command is empty.", allowed=False)

    if is_query_command(cleaned):
        return _classification("query", "Query command can run directly.", confirmation=False, allowlist=False)
    if is_decision_write_command(cleaned):
        return _classification("decision_write", "Decision command persists a snapshot or profile change.")
    if is_candidate_write_command(cleaned):
        return _classification("candidate_write", "Candidate insight command changes pending memory state.")
    if is_research_write_command(cleaned):
        return _classification("research_write", "Research command changes research queue state.")
    if is_maintenance_command(cleaned):
        return _classification("maintenance", "Maintenance command affects external service/session state.")
    if is_coding_task_command(cleaned):
        return _classification("coding_task", "Coding task command changes task queue state.")
    return _classification("unknown", "Command is not recognized by the safe command allowlist.", allowed=False)


def is_write_command(command: str) -> bool:
    return classify_command(command)["category"] in WRITE_CATEGORIES


def is_high_risk_command(command: str) -> bool:
    return classify_command(command)["category"] in {"maintenance"}


def _classification(
    category: str,
    reason: str,
    *,
    confirmation: bool = True,
    allowlist: bool = True,
    allowed: bool = True,
) -> dict[str, Any]:
    return {
        "category": category,
        "requires_confirmation": bool(confirmation and category != "query"),
        "requires_sender_allowlist": bool(allowlist and category != "query"),
        "allowed_from_web": allowed,
        "allowed_from_dingtalk": allowed,
        "reason": reason,
    }
