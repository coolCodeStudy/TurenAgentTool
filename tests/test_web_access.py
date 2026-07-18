from __future__ import annotations

import unittest

from investment_knowledge_mcp.web_access import (
    AccessClass,
    BrowserAccessConfig,
    authorize_request,
    extract_bearer_token,
)


class BrowserAccessConfigTests(unittest.TestCase):
    def test_canonical_token_is_used_when_legacy_aliases_are_absent(self) -> None:
        config = BrowserAccessConfig.resolve(
            canonical="canonical-token",
            command_legacy=None,
            weekly_legacy=None,
        )

        self.assertEqual("canonical-token", config.token)
        self.assertEqual("APP_ACCESS_TOKEN", config.source)
        self.assertFalse(config.conflict)

    def test_equal_legacy_aliases_are_compatible(self) -> None:
        config = BrowserAccessConfig.resolve(
            canonical=None,
            command_legacy="shared-token",
            weekly_legacy="shared-token",
        )

        self.assertEqual("shared-token", config.token)
        self.assertEqual("legacy", config.source)
        self.assertFalse(config.conflict)

    def test_conflicting_configured_aliases_fail_closed_without_values(self) -> None:
        config = BrowserAccessConfig.resolve(
            canonical="canonical-token",
            command_legacy="different-token",
            weekly_legacy=None,
        )

        self.assertIsNone(config.token)
        self.assertIsNone(config.source)
        self.assertTrue(config.conflict)
        self.assertNotIn("canonical-token", repr(config))
        self.assertNotIn("different-token", repr(config))


class BrowserAuthorizationTests(unittest.TestCase):
    def test_public_read_allows_missing_configuration(self) -> None:
        decision = authorize_request(
            AccessClass.PUBLIC_READ,
            method="GET",
            configured=BrowserAccessConfig.resolve(None, None, None),
            supplied_tokens=(),
        )

        self.assertTrue(decision.allowed)
        self.assertIsNone(decision.error_code)

    def test_public_read_protected_write_requires_token_for_post(self) -> None:
        config = BrowserAccessConfig.resolve("configured", None, None)

        read = authorize_request(
            AccessClass.PUBLIC_READ_PROTECTED_WRITE,
            method="GET",
            configured=config,
            supplied_tokens=(),
        )
        write = authorize_request(
            AccessClass.PUBLIC_READ_PROTECTED_WRITE,
            method="POST",
            configured=config,
            supplied_tokens=(),
        )

        self.assertTrue(read.allowed)
        self.assertFalse(write.allowed)
        self.assertEqual("access_required", write.error_code)

    def test_protected_route_distinguishes_configuration_required_and_rejected(self) -> None:
        missing = authorize_request(
            AccessClass.PROTECTED,
            method="POST",
            configured=BrowserAccessConfig.resolve(None, None, None),
            supplied_tokens=(),
        )
        required = authorize_request(
            AccessClass.PROTECTED,
            method="POST",
            configured=BrowserAccessConfig.resolve("configured", None, None),
            supplied_tokens=(),
        )
        rejected = authorize_request(
            AccessClass.PROTECTED,
            method="POST",
            configured=BrowserAccessConfig.resolve("configured", None, None),
            supplied_tokens=("wrong",),
        )

        self.assertEqual("access_not_configured", missing.error_code)
        self.assertEqual("access_required", required.error_code)
        self.assertEqual("access_rejected", rejected.error_code)

    def test_conflicting_configuration_fails_closed(self) -> None:
        decision = authorize_request(
            AccessClass.PROTECTED,
            method="POST",
            configured=BrowserAccessConfig.resolve("one", "two", None),
            supplied_tokens=("one", "two"),
        )

        self.assertFalse(decision.allowed)
        self.assertEqual("access_not_configured", decision.error_code)

    def test_matching_bearer_token_is_accepted(self) -> None:
        supplied = extract_bearer_token("Bearer configured")
        decision = authorize_request(
            AccessClass.PROTECTED,
            method="POST",
            configured=BrowserAccessConfig.resolve("configured", None, None),
            supplied_tokens=(supplied,),
        )

        self.assertTrue(decision.allowed)

    def test_non_bearer_authorization_is_ignored(self) -> None:
        self.assertIsNone(extract_bearer_token("Basic configured"))


if __name__ == "__main__":
    unittest.main()
