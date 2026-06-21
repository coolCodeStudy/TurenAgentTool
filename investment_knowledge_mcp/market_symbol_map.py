from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderSymbol:
    provider: str
    symbol: str
    market: str
    source_url: str | None = None


def resolve_provider_symbol(symbol: str, market: str, provider: str) -> ProviderSymbol:
    cleaned_symbol = symbol.strip().upper()
    cleaned_market = market.strip().upper()
    cleaned_provider = provider.strip().lower()

    if cleaned_provider == "futu":
        futu_symbol = cleaned_symbol if "." in cleaned_symbol else f"{cleaned_market}.{cleaned_symbol}"
        return ProviderSymbol(provider="futu", symbol=futu_symbol, market=cleaned_market)

    if cleaned_provider == "naver_finance_kr":
        if cleaned_market != "KR":
            raise ValueError(f"Naver Finance KR does not support market: {cleaned_market}")
        naver_symbol = _kr_numeric_symbol(cleaned_symbol)
        return ProviderSymbol(
            provider="naver_finance_kr",
            symbol=naver_symbol,
            market="KR",
            source_url=f"https://finance.naver.com/item/main.naver?code={naver_symbol}",
        )

    if cleaned_provider == "naver_finance_kr_daily":
        if cleaned_market != "KR":
            raise ValueError(f"Naver Finance KR daily does not support market: {cleaned_market}")
        naver_symbol = _kr_numeric_symbol(cleaned_symbol)
        return ProviderSymbol(
            provider="naver_finance_kr_daily",
            symbol=naver_symbol,
            market="KR",
            source_url=f"https://finance.naver.com/item/sise_day.naver?code={naver_symbol}&page=1",
        )

    if cleaned_provider == "yahoo_finance":
        if cleaned_market == "KR":
            yahoo_symbol = f"{_kr_numeric_symbol(cleaned_symbol)}.KS"
        elif "." in cleaned_symbol:
            yahoo_symbol = cleaned_symbol
        else:
            yahoo_symbol = cleaned_symbol
        return ProviderSymbol(
            provider="yahoo_finance",
            symbol=yahoo_symbol,
            market=cleaned_market,
            source_url=f"https://finance.yahoo.com/quote/{yahoo_symbol}",
        )

    if cleaned_provider == "yahoo_kospi":
        return ProviderSymbol(
            provider="yahoo_finance",
            symbol="^KS11",
            market="KR",
            source_url="https://finance.yahoo.com/quote/%5EKS11",
        )

    if cleaned_provider == "krx_data_marketplace":
        if cleaned_market != "KR":
            raise ValueError(f"KRX Data Marketplace does not support market: {cleaned_market}")
        krx_symbol = _kr_numeric_symbol(cleaned_symbol)
        return ProviderSymbol(
            provider="krx_data_marketplace",
            symbol=krx_symbol,
            market="KR",
            source_url="https://data.krx.co.kr/contents/MDC/MAIN/main/index.cmd",
        )

    if cleaned_provider == "company_ir_skhynix":
        if cleaned_market != "KR" or _kr_numeric_symbol(cleaned_symbol) != "000660":
            raise ValueError("SK hynix IR mapping is only available for KR.000660")
        return ProviderSymbol(
            provider="company_ir_and_newsroom",
            symbol="000660",
            market="KR",
            source_url="https://www.skhynix.com/ir/UI-FR-IR06/",
        )

    raise ValueError(f"unsupported provider: {provider}")


def _kr_numeric_symbol(symbol: str) -> str:
    value = symbol.split(".", 1)[1] if "." in symbol else symbol
    value = value.strip().upper()
    if not value.isdigit():
        raise ValueError(f"KR provider symbol must be numeric: {symbol}")
    return value.zfill(6)
