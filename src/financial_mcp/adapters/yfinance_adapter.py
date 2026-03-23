"""
yfinance adapter — Tier 1 source for equities, ETFs, options, and FX.

Covers:
  - Real-time / delayed quotes
  - Historical OHLCV prices
  - Options chains
  - Summary fundamentals (P/E, market cap, dividends, …)
  - Recent news headlines
  - Basic forex spot rates
"""

from __future__ import annotations

import logging
from typing import Any

import yfinance as yf

from financial_mcp.cache import cached
from financial_mcp.exceptions import DataParseError, TickerNotFoundError
from financial_mcp.rate_limiter import acquire

logger = logging.getLogger(__name__)

_SOURCE = "yfinance"


def _ticker(symbol: str) -> yf.Ticker:
    acquire(_SOURCE)
    return yf.Ticker(symbol.upper())


def _safe_value(val: Any) -> Any:
    """Convert NaN / None / pandas NA to None for clean JSON serialisation."""
    import math

    if val is None:
        return None
    try:
        if math.isnan(float(val)):
            return None
    except (TypeError, ValueError):
        pass
    return val


# ── Quotes ─────────────────────────────────────────────────────────────────────

@cached("quotes")
def get_quote(ticker: str) -> dict[str, Any]:
    """
    Return a real-time (15-min delayed) quote snapshot for *ticker*.

    Returns keys: symbol, price, open, high, low, volume, market_cap,
    previous_close, change, change_pct, currency, exchange, name.
    """
    t = _ticker(ticker)
    info = t.info
    if not info or info.get("regularMarketPrice") is None:
        raise TickerNotFoundError(ticker, _SOURCE)

    price = _safe_value(info.get("regularMarketPrice") or info.get("currentPrice"))
    prev  = _safe_value(info.get("regularMarketPreviousClose") or info.get("previousClose"))
    change     = round(price - prev, 4) if price is not None and prev is not None else None
    change_pct = round(change / prev * 100, 4) if change is not None and prev else None

    return {
        "symbol":         ticker.upper(),
        "name":           info.get("longName") or info.get("shortName"),
        "price":          price,
        "open":           _safe_value(info.get("regularMarketOpen") or info.get("open")),
        "high":           _safe_value(info.get("regularMarketDayHigh") or info.get("dayHigh")),
        "low":            _safe_value(info.get("regularMarketDayLow") or info.get("dayLow")),
        "volume":         _safe_value(info.get("regularMarketVolume") or info.get("volume")),
        "previous_close": prev,
        "change":         change,
        "change_pct":     change_pct,
        "market_cap":     _safe_value(info.get("marketCap")),
        "currency":       info.get("currency"),
        "exchange":       info.get("exchange"),
        "quote_type":     info.get("quoteType"),
        "source":         _SOURCE,
    }


# ── Price history ──────────────────────────────────────────────────────────────

@cached("eod_prices")
def get_price_history(
    ticker: str,
    period: str = "1y",
    interval: str = "1d",
) -> list[dict[str, Any]]:
    """
    Return OHLCV bars for *ticker*.

    period  : "1d","5d","1mo","3mo","6mo","1y","2y","5y","10y","ytd","max"
    interval: "1m","2m","5m","15m","30m","60m","90m","1h","1d","5d","1wk","1mo","3mo"
    """
    t = _ticker(ticker)
    df = t.history(period=period, interval=interval, auto_adjust=True)
    if df is None or df.empty:
        raise TickerNotFoundError(ticker, _SOURCE)

    records = []
    for ts, row in df.iterrows():
        records.append({
            "date":     ts.isoformat(),
            "open":     _safe_value(row.get("Open")),
            "high":     _safe_value(row.get("High")),
            "low":      _safe_value(row.get("Low")),
            "close":    _safe_value(row.get("Close")),
            "volume":   _safe_value(row.get("Volume")),
        })
    return records


# ── Options chain ──────────────────────────────────────────────────────────────

@cached("quotes")
def get_options_chain(ticker: str, expiration: str | None = None) -> dict[str, Any]:
    """
    Return the options chain for *ticker*.

    If *expiration* is None, the nearest available expiration is used.
    Returns: { expiration, calls: [...], puts: [...] }
    """
    t = _ticker(ticker)
    exps = t.options
    if not exps:
        raise TickerNotFoundError(ticker, _SOURCE)

    exp = expiration if expiration and expiration in exps else exps[0]
    chain = t.option_chain(exp)

    def _df_to_records(df: Any) -> list[dict]:
        if df is None or df.empty:
            return []
        return [
            {k: _safe_value(v) for k, v in row.items()}
            for _, row in df.iterrows()
        ]

    return {
        "ticker":        ticker.upper(),
        "expiration":    exp,
        "available_expirations": list(exps),
        "calls":         _df_to_records(chain.calls),
        "puts":          _df_to_records(chain.puts),
        "source":        _SOURCE,
    }


# ── Fundamentals ───────────────────────────────────────────────────────────────

@cached("fundamentals")
def get_fundamentals(ticker: str) -> dict[str, Any]:
    """
    Return key fundamental metrics for *ticker* from yfinance .info.
    """
    t = _ticker(ticker)
    info = t.info
    if not info:
        raise TickerNotFoundError(ticker, _SOURCE)

    keys = [
        "longName", "sector", "industry", "country", "website", "fullTimeEmployees",
        "marketCap", "enterpriseValue", "trailingPE", "forwardPE", "pegRatio",
        "priceToBook", "priceToSalesTrailing12Months", "enterpriseToRevenue",
        "enterpriseToEbitda", "profitMargins", "operatingMargins", "grossMargins",
        "returnOnAssets", "returnOnEquity", "revenueGrowth", "earningsGrowth",
        "totalRevenue", "grossProfits", "ebitda", "operatingCashflow",
        "freeCashflow", "totalCash", "totalDebt", "debtToEquity",
        "currentRatio", "quickRatio", "beta", "52WeekChange",
        "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "dividendYield",
        "trailingAnnualDividendYield", "payoutRatio", "exDividendDate",
        "sharesOutstanding", "floatShares", "heldPercentInsiders",
        "heldPercentInstitutions", "shortRatio", "shortPercentOfFloat",
        "bookValue", "earningsPerShare", "trailingEps", "forwardEps",
        "targetMeanPrice", "recommendationMean", "recommendationKey",
        "numberOfAnalystOpinions",
    ]
    data: dict[str, Any] = {"symbol": ticker.upper(), "source": _SOURCE}
    for k in keys:
        val = info.get(k)
        data[k] = _safe_value(val) if val is not None else None
    return data


# ── News ───────────────────────────────────────────────────────────────────────

@cached("news")
def get_news(ticker: str, max_items: int = 10) -> list[dict[str, Any]]:
    """Return recent news headlines for *ticker*."""
    t = _ticker(ticker)
    raw = t.news or []
    results = []
    for item in raw[:max_items]:
        results.append({
            "title":       item.get("title"),
            "publisher":   item.get("publisher"),
            "link":        item.get("link"),
            "published_at": item.get("providerPublishTime"),
            "type":        item.get("type"),
            "source":      _SOURCE,
        })
    return results


# ── Forex ──────────────────────────────────────────────────────────────────────

@cached("quotes")
def get_forex_rate(base: str, quote: str = "USD") -> dict[str, Any]:
    """
    Return spot FX rate for *base*/*quote* pair using yfinance.
    e.g. get_forex_rate("EUR", "USD")
    """
    pair = f"{base.upper()}{quote.upper()}=X"
    t = _ticker(pair)
    info = t.info
    price = _safe_value(info.get("regularMarketPrice") or info.get("bid"))
    if price is None:
        raise DataParseError(_SOURCE, f"No price found for FX pair {pair}")
    return {
        "pair":   f"{base.upper()}/{quote.upper()}",
        "rate":   price,
        "source": _SOURCE,
    }
