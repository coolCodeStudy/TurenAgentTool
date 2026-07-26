from __future__ import annotations

import unittest


class EarningsBriefWebTests(unittest.TestCase):
    def test_page_is_working_studio_not_marketing_surface(self) -> None:
        from investment_knowledge_mcp.earnings_brief_studio.web import render_page

        html = render_page()

        self.assertIn('id="company-select"', html)
        self.assertIn('id="period-select"', html)
        self.assertIn('id="export-png"', html)
        self.assertIn('id="brief-root"', html)
        self.assertIn("来源与证据", html)
        self.assertNotIn("Join the waitlist", html)

    def test_browser_script_renders_all_sections_and_canvas_export(self) -> None:
        from investment_knowledge_mcp.earnings_brief_studio.web import render_javascript

        script = render_javascript()

        for marker in (
            "核心判断",
            "核心业绩",
            "管理层信号",
            "收入与利润流",
            "趋势与结构",
            "市场焦点",
            "结构性信号",
            "前瞻情景",
            "来源与证据",
        ):
            self.assertIn(marker, script)
        self.assertIn('canvas.toDataURL("image/png")', script)
        self.assertIn("document.body.appendChild(a)", script)
        self.assertIn("setTimeout", script)
        self.assertIn("1440", script)
        self.assertIn("image/png", script)
        self.assertIn("evidence_state", script)
        self.assertIn("item.claim_kind", script)
        self.assertNotIn('item.display || "未披露"', script)
        self.assertIn('item.evidence_state !== "available"', script)
        self.assertIn("gross_margin_trends", script)
        self.assertIn("margin-bar", script)
        self.assertIn("validation_conditions", script)
        self.assertIn("generated_at", script)
        self.assertIn("source.family", script)
        self.assertIn("data-source-ids", script)
        self.assertIn("scrollIntoView", script)
        self.assertIn("item.candidates", script)
        self.assertIn("12000", script)
        self.assertIn("Array.from", script)
        self.assertNotIn("Math.min(height", script)

    def test_page_uses_shared_navigation_and_mobile_layout(self) -> None:
        from investment_knowledge_mcp.earnings_brief_studio.web import render_page

        html = render_page()

        self.assertIn('href="/earnings-brief-studio" aria-current="page"', html)
        self.assertIn("@media (max-width: 760px)", html)
        self.assertIn("viewport", html)


if __name__ == "__main__":
    unittest.main()
