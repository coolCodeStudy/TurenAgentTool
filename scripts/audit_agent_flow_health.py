from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PROJECT_ROOT / "docs/project-management/Feature-Registry.md"
ACCEPTANCE_QUEUE_PATH = PROJECT_ROOT / "docs/project-management/Acceptance-Queue.md"
DELIVERY_QUEUE_PATH = PROJECT_ROOT / "docs/project-management/Delivery-Queue.md"

ACTIVE_DISPATCH_STATUSES = {"ready_to_dispatch", "dispatched", "in_progress", "returned", "needs_deploy"}
UNHEALTHY_ACCEPTANCE_STATUSES = {"failed", "blocked", "needs_retest"}
DEPLOY_WORDS = ("deploy", "deployment", "restart", "ops api", "github actions", "cloud", "release ref")
RETEST_WORDS = ("retest", "acceptance testing", "acceptance retest", "needs_retest")
GLOBAL_PM_ALLOWED_WORDS = (
    "global deploy",
    "cross-feature",
    "cross feature",
    "stale",
    "credential",
    "permission",
    "conflict",
    "operating-model",
    "operating model",
    "release ref",
    "deploy/ref",
)
WATCH_WORDS = (
    "watch owner",
    "watch path",
    "watch contract",
    "watched item",
    "wake event",
    "wake cadence",
    "runtime watcher",
    "monitoring not active",
    "heartbeat",
    "monitor",
    "this coordinator",
)
WATCH_CONTRACT_ITEM_WORDS = ("watch contract", "watched item", "watch owner/path", "watch owner", "watch path")
WATCH_CONTRACT_WAKE_WORDS = ("wake event", "wake cadence", "next check event", "check cadence", "returned final message")
WATCH_CONTRACT_ARTIFACT_WORDS = ("expected artifact", "expected return", "branch", "commit", "verification", "acceptance result", "blocker")
WATCH_CONTRACT_ACTION_WORDS = (
    "coordinator action",
    "action on wake",
    "return gate",
    "integrate",
    "reject",
    "dispatch",
    "close",
    "deploy decision",
)
PASSIVE_WATCH_PHRASES = ("i will wait", "watch active", "will wait", "wait for")
DEPLOY_DECISION_WORDS = ("self_deploy", "dispatch_deploy_owner", "blocked", "not_required", "deploy decision")
VAGUE_CLOSURE_WORDS = (
    "after deploy",
    "coordinator/ops",
    "someone",
    "later",
    "ready for testing",
    "branch pushed",
    "code fixed",
)
ROUTINE_GLOBAL_PM_RETURN_PHRASES = ("return to global pm", "return to global project manager")


@dataclass(frozen=True)
class DeliveryRow:
    item_id: str
    feature: str
    target_role: str
    status: str
    thread_or_branch: str
    source: str
    expected_result: str
    next_action: str


@dataclass(frozen=True)
class AcceptanceRow:
    item_id: str
    feature: str
    surface: str
    status: str
    severity: str
    evidence: str
    findings: str
    next_action: str


@dataclass(frozen=True)
class RegistryRow:
    feature: str
    product_doc: str
    prd_status: str
    technical_plan: str
    technical_status: str
    implementation: str
    evidence: str
    user_acceptance: str
    known_gaps: str
    next_action: str


@dataclass(frozen=True)
class FlowFinding:
    category: str
    severity: str
    item: str
    detail: str
    next_action: str
    context_required: str = "no"
    context_reason: str = ""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit multi-agent delivery flow health from repo-native project-management state.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when blocker findings exist.")
    parser.add_argument("--feature", help="Filter findings to a feature, queue item, role, or status substring.")
    parser.add_argument(
        "--include-history",
        action="store_true",
        help="Include closed delivery rows and passed acceptance rows in repeated-pattern scans.",
    )
    parser.add_argument(
        "--stale-days",
        type=int,
        default=2,
        help="Flag active dispatch rows whose queue ID date is older than this many days. Default: 2.",
    )
    parser.add_argument(
        "--compare-ref",
        help=(
            "Compare current delivery state with another local ref/branch. "
            "Use this when a coordinator branch may contain newer terminal state that has not been reconciled."
        ),
    )
    args = parser.parse_args()

    delivery_rows = parse_delivery_queue(DELIVERY_QUEUE_PATH)
    acceptance_rows = parse_acceptance_queue(ACCEPTANCE_QUEUE_PATH)
    registry_rows = parse_registry(REGISTRY_PATH)

    findings = audit_flow_health(
        delivery_rows,
        acceptance_rows,
        registry_rows,
        stale_days=args.stale_days,
        today=date.today(),
        include_history=args.include_history,
    )
    if args.compare_ref:
        findings.extend(
            audit_state_reconciliation_needed(
                args.compare_ref,
                delivery_rows,
                acceptance_rows,
                registry_rows,
            )
        )
    if args.feature:
        findings = [finding for finding in findings if matches_finding(finding, args.feature)]

    grouped = group_findings(findings)
    report = {
        "summary": {category: len(items) for category, items in grouped.items()},
        "findings": {category: [asdict(item) for item in items] for category, items in grouped.items()},
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_text_report(grouped)

    if args.strict and has_blocker_findings(findings):
        raise SystemExit(1)


def audit_flow_health(
    delivery_rows: list[DeliveryRow],
    acceptance_rows: list[AcceptanceRow],
    registry_rows: list[RegistryRow],
    *,
    stale_days: int,
    today: date,
    include_history: bool = False,
) -> list[FlowFinding]:
    findings: list[FlowFinding] = []
    findings.extend(audit_active_dispatches(delivery_rows, stale_days=stale_days, today=today))
    findings.extend(audit_return_fanout(delivery_rows))
    findings.extend(audit_owner_routing(delivery_rows))
    findings.extend(audit_context_required(delivery_rows, acceptance_rows, registry_rows))
    findings.extend(audit_repeated_blockers(delivery_rows, acceptance_rows, include_history=include_history))
    findings.extend(audit_deploy_conflicts(delivery_rows, acceptance_rows, registry_rows, include_history=include_history))
    return findings


def audit_state_reconciliation_needed(
    compare_ref: str,
    delivery_rows: list[DeliveryRow],
    acceptance_rows: list[AcceptanceRow],
    registry_rows: list[RegistryRow],
) -> list[FlowFinding]:
    try:
        other_registry = parse_registry_text(read_ref_file(compare_ref, "docs/project-management/Feature-Registry.md"))
        other_acceptance = parse_acceptance_queue_text(
            read_ref_file(compare_ref, "docs/project-management/Acceptance-Queue.md")
        )
        other_delivery = parse_delivery_queue_text(read_ref_file(compare_ref, "docs/project-management/Delivery-Queue.md"))
    except RuntimeError as exc:
        return [
            FlowFinding(
                "state_reconciliation_needed",
                "blocker",
                compare_ref,
                f"Cannot compare coordinator ref `{compare_ref}`: {exc}",
                "Fetch or repair the returned coordinator ref, then rerun the state reconciliation audit.",
                "yes",
                "returned coordinator ref is unavailable",
            )
        ]

    findings: list[FlowFinding] = []
    current_registry = {normalize(row.feature): row for row in registry_rows}
    current_acceptance = group_by_normalized_feature(acceptance_rows)
    current_delivery = group_by_normalized_feature(delivery_rows)

    for other_row in other_registry:
        key = normalize(other_row.feature)
        current_row = current_registry.get(key)
        if not current_row:
            continue
        reasons = registry_advancement_reasons(current_row, other_row)
        acceptance_reasons = acceptance_advancement_reasons(
            current_acceptance.get(key, []),
            [row for row in other_acceptance if normalize(row.feature) == key],
        )
        delivery_reasons = delivery_terminal_reasons(
            current_delivery.get(key, []),
            [row for row in other_delivery if normalize(row.feature) == key],
        )
        all_reasons = reasons + acceptance_reasons + delivery_reasons
        if all_reasons:
            findings.append(
                FlowFinding(
                    "state_reconciliation_needed",
                    "major",
                    other_row.feature,
                    f"`{compare_ref}` appears ahead of current authoritative state: {'; '.join(all_reasons[:4])}.",
                    (
                        "Run the State Reconciliation Gate: cherry-pick or manually port valid feature-specific "
                        "registry/acceptance/delivery/tech-plan state, or record `rejected` / `blocked_with_owner`."
                    ),
                    "yes",
                    "coordinator branch may contain unreconciled durable state",
                )
            )
    return findings


def audit_active_dispatches(
    rows: Iterable[DeliveryRow],
    *,
    stale_days: int,
    today: date,
) -> list[FlowFinding]:
    findings: list[FlowFinding] = []
    for row in rows:
        if row.status not in ACTIVE_DISPATCH_STATUSES:
            continue
        text = row_text(row)
        row_date = queue_date(row.item_id)
        if row.status == "returned":
            findings.append(
                FlowFinding(
                    "returned_not_integrated",
                    "blocker",
                    row.item_id,
                    f"{row.feature} returned from {row.target_role} but is not closed or routed onward.",
                    "Feature Coordinator must apply the Coordinator Return Gate: integrate/reject, update Delivery Queue, and dispatch the next owner or record a blocker.",
                    "yes",
                    "returned role result needs coordinator judgment",
                )
            )
        if row.status in {"dispatched", "in_progress", "needs_deploy"} and not contains_any(text, WATCH_WORDS):
            findings.append(
                FlowFinding(
                    "missing_watch_path",
                    "major",
                    row.item_id,
                    f"{row.feature} is {row.status} but no feature-owned watch path is visible.",
                    "Add watch owner/path, heartbeat, monitor, or an explicit `Monitoring not active` resume action.",
                    "no",
                )
            )
        if row_date and row.status in ACTIVE_DISPATCH_STATUSES:
            age_days = (today - row_date).days
            if age_days > stale_days:
                findings.append(
                    FlowFinding(
                        "stale_coordinator",
                        "major",
                        row.item_id,
                        f"{row.feature} has active dispatch status `{row.status}` for {age_days} days.",
                        "Global PM should check the feature coordinator only if the row is genuinely still active; otherwise close or update the queue row.",
                        "yes",
                        "active queue row appears stale from ID date",
                    )
                )
    return findings


def audit_return_fanout(rows: Iterable[DeliveryRow]) -> list[FlowFinding]:
    returned_by_feature: dict[str, list[DeliveryRow]] = defaultdict(list)
    for row in rows:
        if row.status == "returned":
            returned_by_feature[normalize(row.feature)].append(row)

    findings: list[FlowFinding] = []
    for feature_rows in returned_by_feature.values():
        if len(feature_rows) < 3:
            continue
        item_ids = ", ".join(row.item_id for row in feature_rows[:6])
        findings.append(
            FlowFinding(
                "return_fanout",
                "major",
                feature_rows[0].feature,
                f"{len(feature_rows)} open returned child rows are accumulating for one feature: {item_ids}.",
                "Feature Coordinator must apply the Return Gate and compact accepted evidence into one active release-verification manifest before another child dispatch.",
                "yes",
                "open micro-step returns are hiding the current release state",
            )
        )
    return findings


def audit_owner_routing(rows: Iterable[DeliveryRow]) -> list[FlowFinding]:
    findings: list[FlowFinding] = []
    for row in rows:
        text = row_text(row)
        target = row.target_role.lower()
        if target == "development agent" and contains_any(text, DEPLOY_WORDS + RETEST_WORDS):
            if not contains_any(text, ("implement", "fix", "technical plan", "code", "development")):
                findings.append(
                    FlowFinding(
                        "wrong_owner_suspected",
                        "major",
                        row.item_id,
                        f"{row.feature} is assigned to Development Agent, but the queue text mostly describes deploy/retest routing.",
                        "Feature Coordinator should decide whether this is actually a deploy owner, Acceptance Testing Agent, or coordinator self-deploy step.",
                        "yes",
                        "owner inference may be wrong",
                    )
                )
        if "global project manager" in target and not contains_any(text, GLOBAL_PM_ALLOWED_WORDS):
            findings.append(
                FlowFinding(
                    "global_pm_overuse",
                    "major",
                    row.item_id,
                    f"{row.feature} is routed to Global Project Manager without an obvious global escalation trigger.",
                    "Return normal next-owner routing to the Feature Coordinator; reserve Global PM for cross-feature, stale, credential, deploy conflict, or operating-model issues.",
                    "yes",
                    "possible unnecessary escalation",
                )
            )
        if row.status in ACTIVE_DISPATCH_STATUSES and contains_any(text, ("someone", "later", "after deploy", "coordinator/ops")):
            findings.append(
                FlowFinding(
                    "wrong_owner_suspected",
                    "major",
                    row.item_id,
                    f"{row.feature} uses a vague owner or next step.",
                    "Replace vague owner wording with `self_deploy`, `dispatch_deploy_owner`, `blocked`, or a named role/thread.",
                    "no",
                )
            )
        if row.status in ACTIVE_DISPATCH_STATUSES and contains_any(text, ROUTINE_GLOBAL_PM_RETURN_PHRASES):
            if not contains_any(text, GLOBAL_PM_ALLOWED_WORDS):
                findings.append(
                    FlowFinding(
                        "global_pm_overuse",
                        "major",
                        row.item_id,
                        f"{row.feature} uses `Return to Global PM` without a visible global escalation trigger.",
                        "Keep feature-local routing with the Feature Coordinator unless there is cross-feature conflict, stale recovery, credential/permission, priority, or operating-model defect.",
                        "yes",
                        "possible unnecessary escalation",
                    )
                )
    return findings


def audit_context_required(
    delivery_rows: list[DeliveryRow],
    acceptance_rows: list[AcceptanceRow],
    registry_rows: list[RegistryRow],
) -> list[FlowFinding]:
    findings: list[FlowFinding] = []
    acceptance_by_feature = group_by_normalized_feature(acceptance_rows)
    delivery_by_feature = group_by_normalized_feature(delivery_rows)
    registry_by_feature = {normalize(row.feature): row for row in registry_rows}

    for feature_key, acceptance_group in acceptance_by_feature.items():
        statuses = {row.status for row in acceptance_group}
        registry_row = registry_by_feature.get(feature_key)
        active_delivery = [
            row for row in delivery_by_feature.get(feature_key, []) if row.status in ACTIVE_DISPATCH_STATUSES
        ]
        blocked_recovery = [
            row
            for row in delivery_by_feature.get(feature_key, [])
            if row.status == "blocked" and has_precise_blocked_recovery(row)
        ]
        if len(statuses & UNHEALTHY_ACCEPTANCE_STATUSES) > 0:
            if registry_row and registry_row.user_acceptance == "accepted":
                findings.append(
                    FlowFinding(
                        "context_required",
                        "blocker",
                        registry_row.feature,
                        "Acceptance state is unhealthy but Feature Registry says user acceptance is accepted.",
                        "Read the coordinator context and reconcile the user acceptance state before asking the user for anything else.",
                        "yes",
                        "contradictory acceptance/user-acceptance state",
                    )
                )
            if not active_delivery and not blocked_recovery:
                findings.append(
                    FlowFinding(
                        "context_required",
                        "major",
                        acceptance_group[0].feature,
                        "Acceptance is failed/blocked/needs_retest but no active Delivery Queue follow-up is visible.",
                        "Read coordinator context only if the queue state cannot explain the missing next owner, then add or update the delivery row.",
                        "yes",
                        "unhealthy acceptance without active delivery follow-up",
                    )
                )
    return findings


def audit_repeated_blockers(
    delivery_rows: Iterable[DeliveryRow],
    acceptance_rows: Iterable[AcceptanceRow],
    *,
    include_history: bool,
) -> list[FlowFinding]:
    bucket_items: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for row in delivery_rows:
        if not include_history and row.status not in ACTIVE_DISPATCH_STATUSES:
            continue
        text = row_text(row)
        bucket = blocker_bucket(text)
        if bucket:
            bucket_items[bucket].append((row.item_id, row.feature))
    for row in acceptance_rows:
        if not include_history and row.status not in UNHEALTHY_ACCEPTANCE_STATUSES:
            continue
        if include_history and row.status not in UNHEALTHY_ACCEPTANCE_STATUSES and not contains_any(
            " ".join([row.findings, row.next_action, row.evidence]),
            ("blocked", "failed", "needs_retest", "conflict", "token"),
        ):
            continue
        text = " ".join([row.findings, row.next_action, row.evidence])
        bucket = blocker_bucket(text)
        if bucket:
            bucket_items[bucket].append((row.item_id, row.feature))

    findings: list[FlowFinding] = []
    for bucket, items in sorted(bucket_items.items()):
        unique_items = sorted({item_id for item_id, _feature in items})
        unique_features = {normalize(feature) for _item_id, feature in items}
        if len(unique_items) < 2 or len(unique_features) < 2:
            continue
        findings.append(
            FlowFinding(
                "repeated_blocker",
                "major",
                bucket,
                f"Repeated blocker pattern appears in {len(unique_items)} queue items: {', '.join(unique_items[:6])}.",
                "Consider a durable lesson, protocol update, or audit-script rule if this pattern is still recurring.",
                "yes",
                "repeated blocker pattern may indicate process debt",
            )
        )
    return findings


def audit_deploy_conflicts(
    delivery_rows: Iterable[DeliveryRow],
    acceptance_rows: Iterable[AcceptanceRow],
    registry_rows: Iterable[RegistryRow],
    *,
    include_history: bool,
) -> list[FlowFinding]:
    findings: list[FlowFinding] = []
    sources = []
    for row in delivery_rows:
        if not include_history and row.status not in ACTIVE_DISPATCH_STATUSES:
            continue
        sources.append((row.item_id, row.feature, row_text(row)))
    for row in acceptance_rows:
        if not include_history and row.status not in UNHEALTHY_ACCEPTANCE_STATUSES:
            continue
        sources.append((row.item_id, row.feature, " ".join([row.evidence, row.findings, row.next_action])))
    for row in registry_rows:
        if not include_history and row.implementation not in {"blocked", "in_progress", "needs_review"}:
            continue
        sources.append((row.feature, row.feature, " ".join([row.known_gaps, row.next_action])))

    conflict_items = []
    for item_id, feature, text in sources:
        lower = text.lower()
        if (
            ("deploy" in lower or "release ref" in lower or "current cloud" in lower)
            and contains_any(lower, ("overwrite", "overwritten", "clobber", "conflict", "deploy/ref"))
        ):
            conflict_items.append(f"{item_id} ({feature})")
    if conflict_items:
        findings.append(
            FlowFinding(
                "deploy_conflict",
                "blocker",
                "Production deploy/release refs",
                f"Deploy/ref conflict language appears in {len(conflict_items)} records: {', '.join(conflict_items[:6])}.",
                "Global PM should ensure the next release ref preserves all active feature surfaces before authorizing deploy.",
                "yes",
                "cross-feature deploy conflict requires context",
            )
        )

    active_deploy_rows = [
        row
        for row in delivery_rows
        if (
            row.status in ACTIVE_DISPATCH_STATUSES
            and contains_any(row_text(row), DEPLOY_WORDS)
            and not has_not_required_deploy_decision(row)
        )
    ]
    feature_counts = Counter(normalize(row.feature) for row in active_deploy_rows)
    if len(active_deploy_rows) >= 2 and len(feature_counts) >= 2:
        findings.append(
            FlowFinding(
                "deploy_conflict",
                "major",
                "Active deploy dispatches",
                f"{len(active_deploy_rows)} active deploy-related dispatches span {len(feature_counts)} features.",
                "Check whether deploy serialization is already active and whether release refs need integration before running another deploy.",
                "yes",
                "parallel deploy intents may conflict",
            )
        )
    return findings


def blocker_bucket(text: str) -> str:
    lower = text.lower()
    patterns = [
        ("internal ops credentials", ("ops_api_token", "ops api token", "ops api credential", "private ops credential")),
        ("command workbench token/access", ("command_api_token", "command workbench")),
        ("browser access policy", ("public read", "access token", "unauthorized")),
        ("deploy/ref conflict", ("deploy/ref", "overwritten", "clobber", "release ref", "current deploy")),
        ("acceptance flow blocked", ("acceptance", "needs_retest", "failed", "blocked")),
        ("missing watch path", ("monitoring not active", "watch path", "heartbeat")),
        ("source completeness", ("source completeness", "missing source", "external event", "index provider")),
    ]
    for bucket, markers in patterns:
        if contains_any(lower, markers):
            return bucket
    return ""


def has_not_required_deploy_decision(row: DeliveryRow) -> bool:
    return re.search(
        r"deploy(?:ment)? decision(?:\s+is)?\s*[:=]?\s*`?not_required`?",
        row_text(row).lower(),
    ) is not None


def has_precise_blocked_recovery(row: DeliveryRow) -> bool:
    text = row_text(row).lower()
    return "blocked_with_owner" in text and contains_any(text, ("owner", "provision", "repair", "retry", "dispatch"))


def registry_advancement_reasons(current: RegistryRow, other: RegistryRow) -> list[str]:
    reasons: list[str] = []
    if rank(other.technical_status, TECHNICAL_STATUS_RANK) > rank(current.technical_status, TECHNICAL_STATUS_RANK):
        reasons.append(f"technical status {current.technical_status} -> {other.technical_status}")
    if rank(other.implementation, IMPLEMENTATION_STATUS_RANK) > rank(current.implementation, IMPLEMENTATION_STATUS_RANK):
        reasons.append(f"implementation {current.implementation} -> {other.implementation}")
    if rank(other.evidence, EVIDENCE_STATUS_RANK) > rank(current.evidence, EVIDENCE_STATUS_RANK):
        reasons.append(f"evidence {current.evidence} -> {other.evidence}")
    if rank(other.user_acceptance, USER_ACCEPTANCE_RANK) > rank(current.user_acceptance, USER_ACCEPTANCE_RANK):
        reasons.append(f"user acceptance {current.user_acceptance} -> {other.user_acceptance}")
    if is_missing_plan(current.technical_plan) and not is_missing_plan(other.technical_plan):
        reasons.append(f"technical plan added: {other.technical_plan}")
    return reasons


def acceptance_advancement_reasons(current_rows: list[AcceptanceRow], other_rows: list[AcceptanceRow]) -> list[str]:
    current_by_id = {row.item_id: row for row in current_rows}
    reasons: list[str] = []
    for other in other_rows:
        current = current_by_id.get(other.item_id)
        if not current:
            if rank(other.status, ACCEPTANCE_STATUS_RANK) >= rank("passed", ACCEPTANCE_STATUS_RANK):
                reasons.append(f"acceptance row {other.item_id} exists as {other.status} on compared ref")
            continue
        if rank(other.status, ACCEPTANCE_STATUS_RANK) > rank(current.status, ACCEPTANCE_STATUS_RANK):
            reasons.append(f"acceptance {other.item_id} {current.status} -> {other.status}")
    return reasons


def delivery_terminal_reasons(current_rows: list[DeliveryRow], other_rows: list[DeliveryRow]) -> list[str]:
    current_by_id = {row.item_id: row for row in current_rows}
    reasons: list[str] = []
    for other in other_rows:
        current = current_by_id.get(other.item_id)
        if not current:
            if other.status == "closed":
                reasons.append(f"delivery row {other.item_id} closed on compared ref")
            continue
        if current.status in ACTIVE_DISPATCH_STATUSES and other.status in {"closed", "blocked"}:
            reasons.append(f"delivery {other.item_id} {current.status} -> {other.status}")
    return reasons


def rank(value: str, table: dict[str, int]) -> int:
    return table.get(value.strip().lower(), 0)


def is_missing_plan(value: str) -> bool:
    return value.strip().lower() in {"", "missing", "none", "not_applicable"}


TECHNICAL_STATUS_RANK = {
    "missing": 0,
    "not_started": 0,
    "needs_review": 1,
    "draft": 1,
    "partially_implemented": 2,
    "implemented": 3,
    "superseded": 0,
    "not_applicable": 0,
}
IMPLEMENTATION_STATUS_RANK = {
    "missing": 0,
    "not_started": 0,
    "none": 0,
    "needs_review": 1,
    "in_progress": 2,
    "local_verified": 3,
    "deployed": 4,
    "not_applicable": 0,
}
EVIDENCE_STATUS_RANK = {
    "none": 0,
    "missing": 0,
    "code_reference": 1,
    "local_verified": 2,
    "test_passed": 3,
    "deploy_verified": 4,
    "doc_reference": 1,
}
USER_ACCEPTANCE_RANK = {
    "not_required": 0,
    "pending": 1,
    "needs_reacceptance": 2,
    "rejected": 0,
    "accepted": 3,
}
ACCEPTANCE_STATUS_RANK = {
    "pending": 0,
    "blocked": 0,
    "failed": 0,
    "needs_retest": 1,
    "passed": 2,
}


def parse_delivery_queue(path: Path) -> list[DeliveryRow]:
    rows = parse_table(path, "| ID | Feature | Target Role |")
    return parse_delivery_queue_rows(rows)


def parse_delivery_queue_text(text: str) -> list[DeliveryRow]:
    rows = parse_table_text(text, "| ID | Feature | Target Role |")
    return parse_delivery_queue_rows(rows)


def parse_delivery_queue_rows(rows: list[list[str]]) -> list[DeliveryRow]:
    parsed: list[DeliveryRow] = []
    for cells in rows:
        if len(cells) != 8:
            raise SystemExit(f"Unexpected delivery row shape ({len(cells)} cells): {' | '.join(cells)}")
        parsed.append(DeliveryRow(*[clean_cell(cell) for cell in cells]))
    return parsed


def parse_acceptance_queue(path: Path) -> list[AcceptanceRow]:
    rows = parse_table(path, "| ID | Feature | Surface | Status |")
    return parse_acceptance_queue_rows(rows)


def parse_acceptance_queue_text(text: str) -> list[AcceptanceRow]:
    rows = parse_table_text(text, "| ID | Feature | Surface | Status |")
    return parse_acceptance_queue_rows(rows)


def parse_acceptance_queue_rows(rows: list[list[str]]) -> list[AcceptanceRow]:
    parsed: list[AcceptanceRow] = []
    for cells in rows:
        if len(cells) != 8:
            raise SystemExit(f"Unexpected acceptance row shape ({len(cells)} cells): {' | '.join(cells)}")
        parsed.append(AcceptanceRow(*[clean_cell(cell) for cell in cells]))
    return parsed


def parse_registry(path: Path) -> list[RegistryRow]:
    rows = parse_table(path, "| Feature | Product Doc | PRD Status |")
    return parse_registry_rows(rows)


def parse_registry_text(text: str) -> list[RegistryRow]:
    rows = parse_table_text(text, "| Feature | Product Doc | PRD Status |")
    return parse_registry_rows(rows)


def parse_registry_rows(rows: list[list[str]]) -> list[RegistryRow]:
    parsed: list[RegistryRow] = []
    for cells in rows:
        if len(cells) != 10:
            raise SystemExit(f"Unexpected registry row shape ({len(cells)} cells): {' | '.join(cells)}")
        parsed.append(RegistryRow(*[clean_cell(cell) for cell in cells]))
    return parsed


def parse_table(path: Path, header_prefix: str) -> list[list[str]]:
    if not path.exists():
        raise SystemExit(f"Missing file: {path}")
    return parse_table_text(path.read_text(encoding="utf-8"), header_prefix)


def parse_table_text(text: str, header_prefix: str) -> list[list[str]]:
    table_rows: list[list[str]] = []
    in_table = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith(header_prefix):
            in_table = True
            continue
        if not in_table:
            continue
        if line.startswith("|---"):
            continue
        if not line:
            continue
        if not line.startswith("|"):
            if table_rows and line.startswith("## "):
                break
            continue
        table_rows.append(split_markdown_table_row(line))
    return table_rows


def read_ref_file(ref: str, relative_path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{ref}:{relative_path}"],
        cwd=PROJECT_ROOT,
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        message = clean_cell(result.stderr or result.stdout or "git show failed")
        raise RuntimeError(message)
    return result.stdout


def split_markdown_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def clean_cell(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def queue_date(item_id: str) -> date | None:
    match = re.search(r"-(\d{4})-(\d{2})-(\d{2})-", item_id)
    if not match:
        return None
    try:
        return datetime.strptime("-".join(match.groups()), "%Y-%m-%d").date()
    except ValueError:
        return None


def row_text(row: DeliveryRow) -> str:
    return " ".join(
        [
            row.item_id,
            row.feature,
            row.target_role,
            row.status,
            row.thread_or_branch,
            row.source,
            row.expected_result,
            row.next_action,
        ]
    )


def contains_any(text: str, needles: Iterable[str]) -> bool:
    lower = text.lower()
    return any(needle.lower() in lower for needle in needles)


def has_watch_contract(text: str) -> bool:
    lower = text.lower()
    return (
        contains_any(lower, WATCH_CONTRACT_ITEM_WORDS)
        and contains_any(lower, WATCH_CONTRACT_WAKE_WORDS)
        and contains_any(lower, WATCH_CONTRACT_ARTIFACT_WORDS)
        and contains_any(lower, WATCH_CONTRACT_ACTION_WORDS)
    )


def has_passive_watch_language(text: str) -> bool:
    lower = text.lower()
    if "monitoring not active" in lower:
        return False
    return contains_any(lower, WATCH_WORDS + PASSIVE_WATCH_PHRASES) and not has_watch_contract(lower)


def deploy_needed_without_decision(row: DeliveryRow) -> bool:
    text = row_text(row)
    lower = text.lower()
    if row.status == "needs_deploy":
        return not contains_any(lower, DEPLOY_DECISION_WORDS)
    if contains_any(lower, DEPLOY_WORDS) and contains_any(
        lower,
        ("needs_deploy", "after deploy", "deploy owner", "release ref"),
    ):
        return not contains_any(lower, DEPLOY_DECISION_WORDS)
    return False


def group_by_normalized_feature(rows: Iterable[AcceptanceRow | DeliveryRow]) -> dict[str, list]:
    grouped: dict[str, list] = defaultdict(list)
    for row in rows:
        grouped[normalize(row.feature)].append(row)
    return grouped


def matches_finding(finding: FlowFinding, query: str) -> bool:
    values = [
        finding.category,
        finding.severity,
        finding.item,
        finding.detail,
        finding.next_action,
        finding.context_required,
        finding.context_reason,
    ]
    return any(normalize(query) in normalize(value) for value in values)


def group_findings(findings: Iterable[FlowFinding]) -> dict[str, list[FlowFinding]]:
    order = [
        "deploy_conflict",
        "release_compatibility_missing",
        "state_reconciliation_needed",
        "returned_not_integrated",
        "stale_coordinator",
        "missing_watch_path",
        "wrong_owner_suspected",
        "global_pm_overuse",
        "repeated_blocker",
        "context_required",
    ]
    grouped = {category: [] for category in order}
    for finding in findings:
        grouped.setdefault(finding.category, []).append(finding)
    return {category: items for category, items in grouped.items() if items}


def has_blocker_findings(findings: Iterable[FlowFinding]) -> bool:
    return any(finding.severity == "blocker" for finding in findings)


def print_text_report(grouped: dict[str, list[FlowFinding]]) -> None:
    print("# Agent Flow Health Audit")
    print()
    if not grouped:
        print("- No multi-agent flow health issues found.")
        return
    for category, findings in grouped.items():
        print(f"## {category.replace('_', ' ').title()}")
        for finding in findings:
            print(f"- [{finding.severity}] {finding.item}: {finding.detail}")
            if finding.next_action:
                print(f"  Next: {finding.next_action}")
            if finding.context_required == "yes":
                print(f"  Context required: yes ({finding.context_reason})")
        print()


if __name__ == "__main__":
    main()
