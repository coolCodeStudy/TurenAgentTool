from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from investment_knowledge_mcp.daily_market_review import get_default_providers, normalize_markets
from investment_knowledge_mcp.market_data.session_calendar import DEFAULT_USER_TZ, resolve_review_sessions


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe Daily Market Review provider coverage without saving reports.")
    parser.add_argument("--markets", default="CN,US,HK", help="Comma-separated market list, for example CN,US,HK.")
    parser.add_argument("--output-dir", default="artifacts/provider-probes", help="Directory for sanitized JSON probe artifacts.")
    args = parser.parse_args()

    markets = normalize_markets([item.strip() for item in args.markets.split(",") if item.strip()])
    providers = get_default_providers()
    review_dt = datetime.now(DEFAULT_USER_TZ)
    sessions = resolve_review_sessions(review_dt=review_dt, mode=None, markets=markets)
    payload = {
        "generated_at": review_dt.isoformat(),
        "markets": markets,
        "providers": {},
        "domains": {},
    }

    print("Daily Market Review provider probe")
    print(f"Markets: {', '.join(markets)}")
    for provider in providers:
        capabilities = provider.probe_capabilities(markets)
        payload["providers"][provider.name] = capabilities
        print(f"\nProvider: {provider.name}")
        for market in markets:
            print(f"  {market}: {capabilities.get(market, {})}")
            session = sessions[market]
            payload["domains"].setdefault(market, {})
            for domain, method_name in [
                ("index_quotes", "get_index_quotes"),
                ("market_turnover", "get_market_turnover"),
                ("breadth", "get_breadth"),
                ("hot_stocks", "get_hot_stocks"),
                ("hot_industries", "get_hot_industries"),
            ]:
                method = getattr(provider, method_name)
                result = method(market, session, 5) if domain in {"hot_stocks", "hot_industries"} else method(market, session)
                payload["domains"][market].setdefault(domain, []).append(result.diagnostics())
                print(f"    {domain}: {result.status}")

    output_dir = PROJECT_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"daily_market_provider_probe_{review_dt.strftime('%Y%m%d_%H%M%S')}.json"
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote sanitized probe artifact: {output_path}")


if __name__ == "__main__":
    main()
