from __future__ import annotations

from datetime import date
import unittest

from scripts.audit_agent_flow_health import (
    AcceptanceRow,
    DeliveryRow,
    RegistryRow,
    audit_flow_health,
    has_blocker_findings,
)


def delivery_row(
    item_id: str,
    feature: str,
    target_role: str,
    status: str,
    *,
    source: str = "",
    expected_result: str = "",
    next_action: str = "",
) -> DeliveryRow:
    return DeliveryRow(
        item_id=item_id,
        feature=feature,
        target_role=target_role,
        status=status,
        thread_or_branch="thread `example`",
        source=source,
        expected_result=expected_result,
        next_action=next_action,
    )


def acceptance_row(
    item_id: str,
    feature: str,
    status: str,
    *,
    findings: str = "",
    next_action: str = "",
) -> AcceptanceRow:
    return AcceptanceRow(
        item_id=item_id,
        feature=feature,
        surface="http://example.test",
        status=status,
        severity="major",
        evidence="",
        findings=findings,
        next_action=next_action,
    )


def registry_row(feature: str, *, user_acceptance: str = "pending") -> RegistryRow:
    return RegistryRow(
        feature=feature,
        product_doc="[`PRD.md`](../product/PRD.md)",
        prd_status="ready",
        technical_plan="[`plan.md`](../techplans/plan.md)",
        technical_status="implemented",
        implementation="deployed",
        evidence="deploy_verified",
        user_acceptance=user_acceptance,
        known_gaps="",
        next_action="",
    )


class AgentFlowHealthAuditTests(unittest.TestCase):
    def test_flags_returned_rows_missing_return_gate(self) -> None:
        findings = audit_flow_health(
            [
                delivery_row(
                    "DQ-2026-07-01-001",
                    "Command Workbench",
                    "Acceptance Testing Agent",
                    "returned",
                )
            ],
            [],
            [],
            stale_days=2,
            today=date(2026, 7, 4),
        )

        categories = {finding.category for finding in findings}
        self.assertIn("returned_not_integrated", categories)

    def test_flags_active_dispatch_without_watch_path(self) -> None:
        findings = audit_flow_health(
            [
                delivery_row(
                    "DQ-2026-07-04-001",
                    "Kline Agent",
                    "Development Agent",
                    "dispatched",
                    next_action="Implement the parser fix and return to coordinator.",
                )
            ],
            [],
            [],
            stale_days=2,
            today=date(2026, 7, 4),
        )

        self.assertIn("missing_watch_path", {finding.category for finding in findings})

    def test_flags_global_pm_without_global_trigger(self) -> None:
        findings = audit_flow_health(
            [
                delivery_row(
                    "DQ-2026-07-04-002",
                    "Daily Market Brief",
                    "Global Project Manager",
                    "dispatched",
                    next_action="Please route the next development task.",
                )
            ],
            [],
            [],
            stale_days=2,
            today=date(2026, 7, 4),
        )

        self.assertIn("global_pm_overuse", {finding.category for finding in findings})

    def test_repeated_token_blocker_becomes_learning_candidate(self) -> None:
        findings = audit_flow_health(
            [],
            [
                acceptance_row("AT-2026-07-01-001", "Command Workbench", "blocked", findings="COMMAND_API_TOKEN missing"),
                acceptance_row("AT-2026-07-02-001", "Stock valuation research", "blocked", findings="private token unavailable"),
            ],
            [],
            stale_days=2,
            today=date(2026, 7, 4),
        )

        repeated = [finding for finding in findings if finding.category == "repeated_blocker"]
        self.assertTrue(any(finding.item == "command workbench token/access" for finding in repeated))

    def test_unhealthy_acceptance_without_delivery_followup_requires_context(self) -> None:
        findings = audit_flow_health(
            [],
            [acceptance_row("AT-2026-07-01-001", "Stock valuation research", "blocked")],
            [registry_row("Stock valuation research")],
            stale_days=2,
            today=date(2026, 7, 4),
        )

        context_findings = [finding for finding in findings if finding.category == "context_required"]
        self.assertTrue(context_findings)
        self.assertEqual(context_findings[0].context_required, "yes")

    def test_strict_mode_detects_blocker_severity(self) -> None:
        findings = audit_flow_health(
            [
                delivery_row(
                    "DQ-2026-07-01-001",
                    "Command Workbench",
                    "Acceptance Testing Agent",
                    "returned",
                )
            ],
            [],
            [],
            stale_days=2,
            today=date(2026, 7, 4),
        )

        self.assertTrue(has_blocker_findings(findings))


if __name__ == "__main__":
    unittest.main()
