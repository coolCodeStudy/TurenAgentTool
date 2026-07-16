import unittest

from investment_knowledge_mcp.web_experience import (
    CANONICAL_ACCESS_KEY,
    access_error_payload,
    render_access_session_script,
    render_experience_css,
    render_primary_navigation,
)


class WebExperienceTests(unittest.TestCase):
    def test_primary_navigation_has_stable_order_and_active_state(self) -> None:
        html = render_primary_navigation("weekly_review")
        self.assertLess(html.index("/daily-market-brief"), html.index("/weekly-review"))
        self.assertLess(html.index("/weekly-review"), html.index("/command"))
        self.assertIn('href="/weekly-review" aria-current="page"', html)

    def test_access_script_uses_canonical_and_both_legacy_keys(self) -> None:
        script = render_access_session_script()
        self.assertEqual("investment_knowledge_access_token", CANONICAL_ACCESS_KEY)
        self.assertIn("command_workbench_token", script)
        self.assertIn("weekly_review_web_token", script)
        self.assertIn("legacy_conflict", script)
        self.assertNotIn("console.log", script)

    def test_access_errors_are_distinct_and_recoverable(self) -> None:
        required = access_error_payload("access_required")
        rejected = access_error_payload("access_rejected")
        unavailable = access_error_payload("access_not_configured")
        self.assertNotEqual(required["error"], rejected["error"])
        self.assertNotEqual(rejected["error"], unavailable["error"])
        self.assertTrue(required["recovery"]["next_action"])

    def test_css_contains_shared_focus_and_compact_contracts(self) -> None:
        css = render_experience_css()
        self.assertIn(":focus-visible", css)
        self.assertIn("@media (max-width: 760px)", css)
        self.assertIn("--experience-accent", css)
