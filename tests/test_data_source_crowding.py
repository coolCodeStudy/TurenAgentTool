from __future__ import annotations

from unittest import TestCase

from investment_knowledge_mcp.data_sources.crowding import (
    FUTU_CROWDING_APPROVAL,
    SourceApproval,
    source_is_approved,
)


class CrowdingSourceApprovalTests(TestCase):
    def test_futu_approval_is_private_internal_and_non_redistributable(self) -> None:
        self.assertTrue(source_is_approved("futu_crowding", "private_internal_research"))
        self.assertFalse(source_is_approved("futu_crowding", "public_redistribution"))
        self.assertEqual("account_entitled", FUTU_CROWDING_APPROVAL.access_tier)
        self.assertFalse(FUTU_CROWDING_APPROVAL.redistribution_allowed)
        self.assertEqual(("US", "HK"), FUTU_CROWDING_APPROVAL.enabled_markets)

    def test_unknown_source_or_use_is_not_approved(self) -> None:
        self.assertFalse(source_is_approved("unknown", "private_internal_research"))
        self.assertFalse(source_is_approved("futu_crowding", ""))

    def test_source_approval_rejects_empty_or_duplicate_contract_values(self) -> None:
        with self.assertRaises(ValueError):
            SourceApproval("", "account_entitled", ("private_internal_research",), False, ("US",))
        with self.assertRaises(ValueError):
            SourceApproval("futu", "account_entitled", ("internal", "INTERNAL"), False, ("US",))
        with self.assertRaises(ValueError):
            SourceApproval("futu", "account_entitled", ("internal",), False, ("US", "us"))
