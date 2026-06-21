from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import json
from typing import Any, Callable

from investment_knowledge_mcp.config import AppConfig, get_config
from investment_knowledge_mcp.decision_external_data import probe_external_decision_data, to_probe_result_dict


@dataclass(frozen=True)
class ProbeResult:
    name: str
    supported: bool
    ok: bool
    message: str
    summary: dict[str, Any] | None = None


def probe_futu_decision_data(symbol: str, market: str, config: AppConfig | None = None) -> dict[str, Any]:
    config = config or get_config()
    code = _futu_code(symbol=symbol, market=market)
    try:
        import futu as ft
    except ImportError as exc:
        return {
            "code": code,
            "ok": False,
            "provider": "futu",
            "message": "futu-api is not installed.",
            "results": [
                ProbeResult(
                    name="import_futu",
                    supported=False,
                    ok=False,
                    message=str(exc),
                    summary=None,
                )
            ],
        }

    quote_ctx = ft.OpenQuoteContext(host=config.futu_opend_host, port=config.futu_opend_port)
    try:
        today = date.today()
        start = (today - timedelta(days=180)).isoformat()
        end = today.isoformat()
        results = [
            _probe_api(
                ft=ft,
                ctx=quote_ctx,
                name="request_history_kline",
                call=lambda: quote_ctx.request_history_kline(code, start=start, end=end, max_count=80),
            ),
            _probe_api(
                ft=ft,
                ctx=quote_ctx,
                name="get_market_snapshot",
                call=lambda: quote_ctx.get_market_snapshot([code]),
            ),
            _probe_api(
                ft=ft,
                ctx=quote_ctx,
                name="get_valuation_detail",
                call=lambda: quote_ctx.get_valuation_detail(code),
            ),
            _probe_api(
                ft=ft,
                ctx=quote_ctx,
                name="get_research_analyst_consensus",
                call=lambda: quote_ctx.get_research_analyst_consensus(code),
            ),
        ]
    finally:
        quote_ctx.close()

    return {
        "code": code,
        "ok": any(item.ok for item in results),
        "provider": "futu",
        "opend": {"host": config.futu_opend_host, "port": config.futu_opend_port},
        "results": results,
    }


def probe_decision_data_coverage(symbol: str, market: str, config: AppConfig | None = None) -> dict[str, Any]:
    futu_payload = probe_futu_decision_data(symbol=symbol, market=market, config=config)
    external_payload = probe_external_decision_data(symbol=symbol, market=market)
    results: list[Any] = []
    results.extend(futu_payload.get("results") or [])
    results.extend(to_probe_result_dict(item) for item in external_payload.get("results") or [])
    return {
        "code": f"{market.strip().upper()}.{symbol.strip().upper()}",
        "ok": bool(futu_payload.get("ok") or external_payload.get("ok")),
        "provider": "decision_data_provider_ladder",
        "opend": futu_payload.get("opend"),
        "results": results,
    }


def render_probe_result(payload: dict[str, Any]) -> str:
    lines = [
        f"Decision data probe: {payload.get('code')}",
        f"Provider: {payload.get('provider', 'futu')}",
    ]
    opend = payload.get("opend") or {}
    if opend:
        lines.append(f"OpenD: {opend.get('host')}:{opend.get('port')}")
    lines.append("")
    for item in payload.get("results") or []:
        if isinstance(item, ProbeResult):
            result = item
        else:
            result = ProbeResult(**item)
        status = "ok" if result.ok else ("unsupported" if not result.supported else "failed")
        lines.append(f"- {result.name}: {status}")
        lines.append(f"  message: {result.message}")
        if result.summary:
            summary = json.dumps(result.summary, ensure_ascii=False, sort_keys=True)
            if len(summary) > 1200:
                summary = summary[:1197] + "..."
            lines.append(f"  summary: {summary}")
    return "\n".join(lines)


def _probe_api(ft: Any, ctx: Any, name: str, call: Callable[[], tuple[Any, Any] | tuple[Any, Any, Any]]) -> ProbeResult:
    if not hasattr(ctx, name):
        return ProbeResult(name=name, supported=False, ok=False, message="method is not available in installed futu-api")
    try:
        response = call()
    except Exception as exc:
        return ProbeResult(name=name, supported=True, ok=False, message=f"{type(exc).__name__}: {exc}")
    ret = response[0]
    data = response[1] if len(response) > 1 else None
    if ret != ft.RET_OK:
        return ProbeResult(name=name, supported=True, ok=False, message=str(data), summary=None)
    return ProbeResult(name=name, supported=True, ok=True, message="RET_OK", summary=_summarize_data(data))


def _summarize_data(data: Any) -> dict[str, Any]:
    if hasattr(data, "to_dict"):
        records = data.head(3).to_dict(orient="records") if hasattr(data, "head") else data.to_dict()
        return {
            "type": "dataframe",
            "rows": int(len(data)) if hasattr(data, "__len__") else None,
            "columns": list(getattr(data, "columns", [])),
            "sample": _json_safe(records),
        }
    if isinstance(data, dict):
        return {"type": "dict", "keys": sorted(data.keys()), "sample": _json_safe(data)}
    if isinstance(data, list):
        return {"type": "list", "rows": len(data), "sample": _json_safe(data[:3])}
    return {"type": type(data).__name__, "sample": _json_safe(data)}


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except TypeError:
        if isinstance(value, dict):
            return {str(k): _json_safe(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_json_safe(item) for item in value]
        return str(value)


def _futu_code(symbol: str, market: str) -> str:
    cleaned_symbol = symbol.strip().upper()
    cleaned_market = market.strip().upper()
    if "." in cleaned_symbol:
        return cleaned_symbol
    return f"{cleaned_market}.{cleaned_symbol}"
