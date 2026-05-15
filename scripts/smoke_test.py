from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from investment_knowledge_mcp.db import run_schema
from investment_knowledge_mcp.repository import (
    add_knowledge_item,
    add_user_insight,
    link_stock_to_sector,
    search_stock,
    upsert_sector_tree,
    upsert_stock_profile,
)


def main() -> None:
    run_schema()

    stock = upsert_stock_profile(
        symbol="00700",
        market="HK",
        name="腾讯控股",
        core_business="互联网增值服务、金融科技及企业服务、网络广告。",
        stock_character="流动性好，受互联网监管和平台经济预期影响明显。",
        notable_history="曾长期作为港股互联网龙头和恒生科技权重股。",
    )
    sector_tree = upsert_sector_tree(
        path=["互联网", "平台经济", "游戏"],
        description="以互联网平台和游戏业务为核心的细分板块。",
        recent_status="关注版号、广告复苏和 AI 应用落地。",
    )
    relation = link_stock_to_sector(
        stock_id=stock["id"],
        sector_id=sector_tree["leaf"]["id"],
        relation_type="main",
        confidence=0.9,
        confirmed_by_user=True,
    )
    knowledge = add_knowledge_item(
        target_type="stock",
        target_id=stock["id"],
        knowledge_type="business",
        content="腾讯的核心业务包含游戏、社交网络、广告、金融科技及企业服务。",
        confidence=0.8,
        confirmed_by_user=True,
    )
    insight = add_user_insight(
        target_type="stock",
        target_id=stock["id"],
        insight="腾讯更适合看中长期基本面和港股互联网情绪修复，不适合只看一天波动。",
        normalized_summary="用户倾向将腾讯作为中长期基本面和情绪修复标的观察。",
        tags=["中长期", "港股互联网", "情绪修复"],
    )
    result = search_stock(symbol="00700", market="HK")

    assert result["stock"]["id"] == stock["id"]
    assert result["sectors"][0]["relation_id"] == relation["id"]
    assert result["knowledge_items"][0]["id"] == knowledge["id"]
    assert result["user_insights"][0]["id"] == insight["id"]

    print("Smoke test passed.")
    print(
        {
            "stock": result["stock"]["symbol"],
            "sector_count": len(result["sectors"]),
            "knowledge_count": len(result["knowledge_items"]),
            "insight_count": len(result["user_insights"]),
        }
    )


if __name__ == "__main__":
    main()
