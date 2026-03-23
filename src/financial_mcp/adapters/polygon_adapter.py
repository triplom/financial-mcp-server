"""
Polygon.io adapter — Tier 2 source for real-time crypto, forex, and US equities.

Free tier: 5 REST req/min, unlimited WebSocket for crypto.
This adapter uses REST only (WebSocket is outside MCP scope).

Requires: POLYGON_API_KEY in environment.
"""

from __future__ import annotations

import logging
from typing import Any

from financial_mcp.cache import cached
from financial_mcp.config import CONFIG
from financial_mcp.exceptions import MissingAPIKeyError, SourceUnavailableError, TickerNotFoundError
from financial_mcp.rate_limiter import acquire

logger = logging.getLogger(__name__)

_SOURCE = "polygon"


def _client():
    """Lazy-import polygon client to avoid startup error if key is missing."""
    if not CONFIG.keys.has("polygon"):
        raise MissingAPIKeyError("Polygon.io", "POLYGON_API_KEY")
    from polygon import RESTClient
    return RESTClient(api_key=CONFIG.keys.polygon)


# ── Equities ───────────────────────────────────────────────────────────────────

@cached("quotes")
def get_snapshot(ticker: str) -> dict[str, Any]:
    """Return a full market snapshot for a US equity ticker."""
    acquire(_SOURCE)
    try:
        client = _client()
        snap = client.get_snapshot_ticker("stocks", ticker.upper())
    except Exception as exc:
        if "not found" in str(exc).lower() or "404" in str(exc):
            raise TickerNotFoundError(ticker, _SOURCE) from exc
        raise SourceUnavailableError(_SOURCE, str(exc)) from exc

    day   = getattr(snap, "day", None) or {}
    prev  = getattr(snap, "prev_day", None) or {}
    min_  = getattr(snap, "min", None) or {}

    def _attr(obj: Any, key: str) -> Any:
        if isinstance(obj, dict):
            return obj.get(key)
        return getattr(obj, key, None)

    return {
        "symbol":        ticker.upper(),
        "price":         _attr(day, "c") or _attr(min_, "c"),
        "open":          _attr(day, "o"),
        "high":          _attr(day, "h"),
        "low":           _attr(day, "l"),
        "close":         _attr(day, "c"),
        "volume":        _attr(day, "v"),
        "vwap":          _attr(day, "vw"),
        "prev_close":    _attr(prev, "c"),
        "change_pct":    getattr(snap, "todays_change_perc", None),
        "source":        _SOURCE,
    }


@cached("eod_prices")
def get_aggregates(
    ticker: str,
    multiplier: int = 1,
    timespan: str = "day",
    from_date: str = "2023-01-01",
    to_date: str = "2024-01-01",
    limit: int = 252,
) -> list[dict[str, Any]]:
    """
    Return OHLCV aggregate bars for *ticker*.

    timespan: "minute"|"hour"|"day"|"week"|"month"|"quarter"|"year"
    """
    acquire(_SOURCE)
    try:
        client = _client()
        aggs = client.get_aggs(
            ticker.upper(),
            multiplier=multiplier,
            timespan=timespan,
            from_=from_date,
            to=to_date,
            limit=limit,
            adjusted=True,
        )
    except Exception as exc:
        raise SourceUnavailableError(_SOURCE, str(exc)) from exc

    return [
        {
            "timestamp_ms": bar.timestamp,
            "open":   bar.open,
            "high":   bar.high,
            "low":    bar.low,
            "close":  bar.close,
            "volume": bar.volume,
            "vwap":   getattr(bar, "vwap", None),
        }
        for bar in (aggs or [])
    ]


# ── Crypto ─────────────────────────────────────────────────────────────────────

@cached("crypto")
def get_crypto_snapshot(ticker: str) -> dict[str, Any]:
    """
    Return snapshot for a crypto pair.
    ticker format: "X:BTCUSD" or just "BTCUSD" (prefix X: added automatically).
    """
    symbol = ticker.upper()
    if not symbol.startswith("X:"):
        symbol = f"X:{symbol}"
    acquire(_SOURCE)
    try:
        client = _client()
        snap = client.get_snapshot_ticker("crypto", symbol)
    except Exception as exc:
        if "not found" in str(exc).lower() or "404" in str(exc):
            raise TickerNotFoundError(ticker, _SOURCE) from exc
        raise SourceUnavailableError(_SOURCE, str(exc)) from exc

    day = getattr(snap, "day", None) or {}

    def _attr(obj: Any, key: str) -> Any:
        if isinstance(obj, dict):
            return obj.get(key)
        return getattr(obj, key, None)

    return {
        "pair":          symbol,
        "price":         _attr(day, "c"),
        "open":          _attr(day, "o"),
        "high":          _attr(day, "h"),
        "low":           _attr(day, "l"),
        "volume":        _attr(day, "v"),
        "vwap":          _attr(day, "vw"),
        "change_pct":    getattr(snap, "todays_change_perc", None),
        "source":        _SOURCE,
    }


# ── Forex ──────────────────────────────────────────────────────────────────────

@cached("quotes")
def get_forex_snapshot(from_currency: str, to_currency: str = "USD") -> dict[str, Any]:
    """
    Return current FX rate from Polygon.
    ticker format: "C:EURUSD"
    """
    symbol = f"C:{from_currency.upper()}{to_currency.upper()}"
    acquire(_SOURCE)
    try:
        client = _client()
        snap = client.get_snapshot_ticker("forex", symbol)
    except Exception as exc:
        if "not found" in str(exc).lower() or "404" in str(exc):
            raise TickerNotFoundError(f"{from_currency}/{to_currency}", _SOURCE) from exc
        raise SourceUnavailableError(_SOURCE, str(exc)) from exc

    day = getattr(snap, "day", None) or {}

    def _attr(obj: Any, key: str) -> Any:
        if isinstance(obj, dict):
            return obj.get(key)
        return getattr(obj, key, None)

    return {
        "pair":       symbol,
        "rate":       _attr(day, "c"),
        "open":       _attr(day, "o"),
        "high":       _attr(day, "h"),
        "low":        _attr(day, "l"),
        "change_pct": getattr(snap, "todays_change_perc", None),
        "source":     _SOURCE,
    }


# ── Ticker details ─────────────────────────────────────────────────────────────

@cached("fundamentals")
def get_ticker_details(ticker: str) -> dict[str, Any]:
    """Return company details from Polygon reference data."""
    acquire(_SOURCE)
    try:
        client = _client()
        details = client.get_ticker_details(ticker.upper())
    except Exception as exc:
        if "not found" in str(exc).lower() or "404" in str(exc):
            raise TickerNotFoundError(ticker, _SOURCE) from exc
        raise SourceUnavailableError(_SOURCE, str(exc)) from exc

    return {
        "symbol":         getattr(details, "ticker", ticker.upper()),
        "name":           getattr(details, "name", None),
        "description":    getattr(details, "description", None),
        "sic_code":       getattr(details, "sic_code", None),
        "sic_description": getattr(details, "sic_description", None),
        "market_cap":     getattr(details, "market_cap", None),
        "employees":      getattr(details, "total_employees", None),
        "homepage":       getattr(details, "homepage_url", None),
        "list_date":      getattr(details, "list_date", None),
        "locale":         getattr(details, "locale", None),
        "market":         getattr(details, "market", None),
        "currency":       getattr(details, "currency_name", None),
        "source":         _SOURCE,
    }
