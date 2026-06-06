from __future__ import annotations

import re
from typing import Any


FACT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("revenue", re.compile(r"(?i)(revenue|收入|营业收入|总收入)[^。\n；]{0,120}")),
    ("profit", re.compile(r"(?i)(profit|net income|净利润|利润|亏损)[^。\n；]{0,120}")),
    ("gross_margin", re.compile(r"(?i)(gross margin|毛利率)[^。\n；]{0,120}")),
    ("gross_profit", re.compile(r"(?i)(gross profit|毛利)[^。\n；]{0,120}")),
    ("research_development", re.compile(r"(?i)(research and development|R&D|研发)[^。\n；]{0,120}")),
    ("guidance", re.compile(r"(?i)(guidance|outlook|指引|展望)[^。\n；]{0,160}")),
    ("nav", re.compile(r"(?i)(NAV as of|NAV\b)[^。\n；]{0,120}")),
    ("sec_yield", re.compile(r"(?i)(30 Day SEC Yield)[^。\n；]{0,120}")),
    ("trailing_yield", re.compile(r"(?i)(12m Trailing Yield)[^。\n；]{0,120}")),
    ("expense_ratio", re.compile(r"(?i)(Expense Ratio)[^。\n；]{0,120}")),
    ("net_assets", re.compile(r"(?i)(Net Assets of Fund|net assets)[^。\n；]{0,120}")),
    ("holdings_count", re.compile(r"(?i)(Number of Holdings)[^。\n；]{0,120}")),
    ("effective_duration", re.compile(r"(?i)(Effective Duration)[^。\n；]{0,120}")),
    ("weighted_maturity", re.compile(r"(?i)(Weighted Avg Maturity)[^。\n；]{0,120}")),
    ("risk", re.compile(r"(?i)(risk|风险)[^。\n；]{0,180}")),
]


def extract_source_facts(draft: dict[str, Any], max_facts_per_source: int = 12) -> dict[str, Any]:
    facts: list[dict[str, Any]] = []
    for source in draft.get("sources") or []:
        if not isinstance(source, dict):
            continue
        source_key = source.get("key")
        excerpt = source.get("content_excerpt") or ""
        if not isinstance(source_key, str) or not isinstance(excerpt, str) or not excerpt.strip():
            continue
        source_facts = _extract_from_text(source_key=source_key, text=excerpt)
        facts.extend(source_facts[:max_facts_per_source])

    return {
        "stock": draft.get("stock") or {},
        "fact_count": len(facts),
        "facts": facts,
    }


def _extract_from_text(source_key: str, text: str) -> list[dict[str, Any]]:
    normalized = " ".join(text.split())
    facts: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for fact_type, pattern in FACT_PATTERNS:
        for match in pattern.finditer(normalized):
            snippet = match.group(0).strip()
            numbers = extract_numbers(snippet)
            if not numbers and fact_type not in {"risk", "guidance"}:
                continue
            key = (fact_type, snippet[:160])
            if key in seen:
                continue
            seen.add(key)
            facts.append(
                {
                    "source_key": source_key,
                    "fact_type": fact_type,
                    "excerpt": snippet,
                    "char_start": match.start(),
                    "char_end": match.end(),
                    "numbers": numbers,
                }
            )
    return facts


def extract_numbers(text: str) -> list[str]:
    values = re.findall(r"[-+]?\d[\d,]*(?:\.\d+)?%?", text)
    return [_normalize_number(value) for value in values if value.strip()]


def _normalize_number(value: str) -> str:
    return value.replace(",", "").strip()
