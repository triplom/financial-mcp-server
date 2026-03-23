"""
Tiingo adapter — Tier 2 source for validated historical stock data and news.

Strengths over yfinance:
  - Data validated/corrected by Tiingo's data team
  - History back to 1962 for many US equities
  - Best-in-class news API with ticker and topic tagging

Free tier: 50 req/hr, 1000 unique tickers/month.
Requires: TIINGO_API_KEY in environment.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from financial_mcp.cache import cached
from financial_mcp.config import CONFIG
from financial_mcp.exceptions import MissingAPIKeyError, SourceUnavailableError, TickerNotFoundError
from financial_mcp.rate_limiter import acquire

logger = logging.getLogger(__name__)

_SOURCE = "tiingo"
_BASE = "https://api.tiingo.com"


def _headers() -> dict[str, str]:
    if not CONFIG.keys.has("tiingo"):
        raise MissingAPIKeyError("Tiingo", "TIINGO_API_KEY")
    return {
        "Authorization": f"Token {CONFIG.keys.tiingo}",
        "Content-Type":  "application/json",
    }


def _get(path: str, params: dict | None = None) -> Any:
    acquire(_SOURCE)
    try:
        resp = httpx.get(f"{_BASE}{path}", headers=_headers(), params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise TickerNotFoundError(path, _SOURCE) from exc
        raise SourceUnavailableError(_SOURCE, str(exc)) from exc
    except Exception as exc:
        raise SourceUnavailableError(_SOURCE, str(exc)) from exc


# ── End-of-day prices ──────────────────────────────────────────────────────────

@cached("eod_prices")
def get_price_history(
    ticker: str,
    start_date: str | None = None,
    end_date: str | None = None,
    frequency: str = "daily",
) -> list[dict[str, Any]]:
    """
    Return OHLCV price history from Tiingo.

    frequency: "daily" | "weekly" | "monthly" | "annually"
    start_date / end_date: "YYYY-MM-DD"
    """
    params: dict[str, Any] = {"resampleFreq": frequency}
    if start_date:
        params["startDate"] = start_date
    if end_date:
        params["endDate"] = end_date

    data = _get(f"/tiingo/daily/{ticker.upper()}/prices", params=params)
    if not data:
        raise TickerNotFoundError(ticker, _SOURCE)

    return [
        {
            "date":          row.get("date", "")[:10],
            "open":          row.get("adjOpen"),
            "high":          row.get("adjHigh"),
            "low":           row.get("adjLow"),
            "close":         row.get("adjClose"),
            "volume":        row.get("adjVolume"),
            "unadj_close":   row.get("close"),
            "dividend":      row.get("divCash"),
            "split_factor":  row.get("splitFactor"),
        }
        for row in data
    ]


# ── Latest quote ───────────────────────────────────────────────────────────────

@cached("quotes")
def get_quote(ticker: str) -> dict[str, Any]:
    """Return the latest end-of-day quote for *ticker*."""
    data = _get(f"/tiingo/daily/{ticker.upper()}/prices")
    if not data:
        raise TickerNotFoundError(ticker, _SOURCE)
    row = data[-1]
    return {
        "symbol":        ticker.upper(),
        "date":          row.get("date", "")[:10],
        "close":         row.get("adjClose"),
        "open":          row.get("adjOpen"),
        "high":          row.get("adjHigh"),
        "low":           row.get("adjLow"),
        "volume":        row.get("adjVolume"),
        "source":        _SOURCE,
    }


# ── Metadata ───────────────────────────────────────────────────────────────────

@cached("fundamentals")
def get_metadata(ticker: str) -> dict[str, Any]:
    """Return Tiingo metadata for *ticker* (description, exchange, start date, etc.)."""
    data = _get(f"/tiingo/daily/{ticker.upper()}")
    return {
        "symbol":        data.get("ticker"),
        "name":          data.get("name"),
        "description":   data.get("description"),
        "exchange":      data.get("exchangeCode"),
        "start_date":    data.get("startDate"),
        "end_date":      data.get("endDate"),
        "source":        _SOURCE,
    }


# ── News ───────────────────────────────────────────────────────────────────────

@cached("news")
def get_news(
    tickers: list[str] | str | None = None,
    tags: list[str] | str | None = None,
    limit: int = 20,
    start_date: str | None = None,
) -> list[dict[str, Any]]:
    """
    Return news articles from Tiingo with ticker and topic tagging.

    Args:
        tickers:    One or more ticker symbols (e.g. ["AAPL", "MSFT"]).
        tags:       Topic tags (e.g. ["earnings", "merger"]).
        limit:      Max articles to return (max 1000).
        start_date: Only articles after this ISO date.
    """
    params: dict[str, Any] = {"limit": min(limit, 1000)}

    if tickers:
        t = tickers if isinstance(tickers, str) else ",".join(tickers)
        params["tickers"] = t.upper()
    if tags:
        params["tags"] = tags if isinstance(tags, str) else ",".join(tags)
    if start_date:
        params["startDate"] = start_date

    data = _get("/tiingo/news", params=params)
    return [
        {
            "id":           article.get("id"),
            "title":        article.get("title"),
            "description":  article.get("description"),
            "url":          article.get("url"),
            "source":       article.get("source"),
            "published_at": article.get("publishedDate"),
            "tickers":      article.get("tickers", []),
            "tags":         article.get("tags", []),
            "data_source":  _SOURCE,
        }
        for article in (data or [])
    ]


# ── Crypto (Tiingo also covers crypto via IEX) ─────────────────────────────────

@cached("crypto")
def get_crypto_price(ticker: str, vs_currency: str = "usd") -> dict[str, Any]:
    """
    Return latest crypto price from Tiingo crypto endpoint.
    ticker: CoinGecko-style base symbol, e.g. "btc", "eth"
    """
    pair = f"{ticker.lower()}{vs_currency.lower()}"
    data = _get(f"/tiingo/crypto/prices", params={"tickers": pair})
    if not data:
        raise TickerNotFoundError(ticker, _SOURCE)
    row = data[0]
    price_data = row.get("priceData", [{}])[-1]
    return {
        "pair":       pair,
        "price":      price_data.get("lastPrice"),
        "bid":        price_data.get("bidPrice"),
        "ask":        price_data.get("askPrice"),
        "volume_24h": price_data.get("volume24h"),
        "timestamp":  price_data.get("date"),
        "source":     _SOURCE,
    }
