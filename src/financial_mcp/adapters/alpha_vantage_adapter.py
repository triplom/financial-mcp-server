"""
Alpha Vantage adapter — Tier 3 / optional source.

Primary value: technical indicators and commodity prices.
WARNING: Free tier is only 25 requests/day (as of 2024).
The rate limiter is set to 1 req/12s which still exhausts the daily quota in
5 minutes if called unchecked.  Every function here is aggressively cached.

Requires: ALPHA_VANTAGE_API_KEY in environment.
"""

from __future__ import annotations

import logging
from typing import Any

from financial_mcp.cache import cached
from financial_mcp.config import CONFIG
from financial_mcp.exceptions import MissingAPIKeyError, RateLimitError, SourceUnavailableError
from financial_mcp.rate_limiter import acquire

logger = logging.getLogger(__name__)

_SOURCE = "alpha_vantage"


def _client():
    if not CONFIG.keys.has("alpha_vantage"):
        raise MissingAPIKeyError("Alpha Vantage", "ALPHA_VANTAGE_API_KEY")
    from alpha_vantage.timeseries import TimeSeries
    from alpha_vantage.techindicators import TechIndicators
    from alpha_vantage.commodities import Commodities
    return (
        TimeSeries(key=CONFIG.keys.alpha_vantage, output_format="pandas"),
        TechIndicators(key=CONFIG.keys.alpha_vantage, output_format="pandas"),
        Commodities(key=CONFIG.keys.alpha_vantage, output_format="pandas"),
    )


def _check_quota_error(exc: Exception) -> None:
    msg = str(exc).lower()
    if "rate limit" in msg or "api call frequency" in msg or "25 calls" in msg:
        raise RateLimitError(_SOURCE) from exc


# ── Technical indicators ───────────────────────────────────────────────────────

@cached("eod_prices")
def get_rsi(ticker: str, interval: str = "daily", time_period: int = 14) -> list[dict[str, Any]]:
    """Return RSI values for *ticker*."""
    acquire(_SOURCE)
    try:
        _, ti, _ = _client()
        data, _ = ti.get_rsi(symbol=ticker.upper(), interval=interval, time_period=time_period)
    except Exception as exc:
        _check_quota_error(exc)
        raise SourceUnavailableError(_SOURCE, str(exc)) from exc

    return [
        {"date": str(idx.date()), "rsi": round(float(row["RSI"]), 4)}
        for idx, row in data.iterrows()
    ][:50]


@cached("eod_prices")
def get_macd(
    ticker: str,
    interval: str = "daily",
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> list[dict[str, Any]]:
    """Return MACD, MACD Signal, and MACD Hist for *ticker*."""
    acquire(_SOURCE)
    try:
        _, ti, _ = _client()
        data, _ = ti.get_macd(
            symbol=ticker.upper(),
            interval=interval,
            fastperiod=fast,
            slowperiod=slow,
            signalperiod=signal,
        )
    except Exception as exc:
        _check_quota_error(exc)
        raise SourceUnavailableError(_SOURCE, str(exc)) from exc

    return [
        {
            "date":        str(idx.date()),
            "macd":        round(float(row["MACD"]), 6),
            "signal":      round(float(row["MACD_Signal"]), 6),
            "histogram":   round(float(row["MACD_Hist"]), 6),
        }
        for idx, row in data.iterrows()
    ][:50]


@cached("eod_prices")
def get_bbands(
    ticker: str,
    interval: str = "daily",
    time_period: int = 20,
) -> list[dict[str, Any]]:
    """Return Bollinger Bands (upper, middle, lower) for *ticker*."""
    acquire(_SOURCE)
    try:
        _, ti, _ = _client()
        data, _ = ti.get_bbands(symbol=ticker.upper(), interval=interval, time_period=time_period)
    except Exception as exc:
        _check_quota_error(exc)
        raise SourceUnavailableError(_SOURCE, str(exc)) from exc

    return [
        {
            "date":   str(idx.date()),
            "upper":  round(float(row["Real Upper Band"]), 4),
            "middle": round(float(row["Real Middle Band"]), 4),
            "lower":  round(float(row["Real Lower Band"]), 4),
        }
        for idx, row in data.iterrows()
    ][:50]


@cached("eod_prices")
def get_sma(ticker: str, interval: str = "daily", time_period: int = 50) -> list[dict[str, Any]]:
    """Return Simple Moving Average for *ticker*."""
    acquire(_SOURCE)
    try:
        _, ti, _ = _client()
        data, _ = ti.get_sma(symbol=ticker.upper(), interval=interval, time_period=time_period)
    except Exception as exc:
        _check_quota_error(exc)
        raise SourceUnavailableError(_SOURCE, str(exc)) from exc

    return [
        {"date": str(idx.date()), "sma": round(float(row["SMA"]), 4)}
        for idx, row in data.iterrows()
    ][:50]


# ── Commodities ────────────────────────────────────────────────────────────────

@cached("eod_prices")
def get_commodity_price(commodity: str, interval: str = "monthly") -> list[dict[str, Any]]:
    """
    Return commodity price series.

    commodity: "wti" | "brent" | "natural_gas" | "copper" | "aluminum" |
               "wheat" | "corn" | "cotton" | "sugar" | "coffee" | "global_price_of_cocoa"
    interval : "daily" | "weekly" | "monthly"
    """
    _commodity_map = {
        "wti":          "get_crude_oil_prices_WTI",
        "brent":        "get_crude_oil_prices_Brent",
        "natural_gas":  "get_natural_gas",
        "copper":       "get_copper",
        "aluminum":     "get_aluminum",
        "wheat":        "get_wheat",
        "corn":         "get_corn",
        "cotton":       "get_cotton",
        "sugar":        "get_sugar",
        "coffee":       "get_coffee",
    }
    method_name = _commodity_map.get(commodity.lower())
    if not method_name:
        raise ValueError(
            f"Unknown commodity '{commodity}'. Valid: {list(_commodity_map)}"
        )
    acquire(_SOURCE)
    try:
        _, _, comm = _client()
        method = getattr(comm, method_name)
        data, _ = method(interval=interval)
    except Exception as exc:
        _check_quota_error(exc)
        raise SourceUnavailableError(_SOURCE, str(exc)) from exc

    return [
        {"date": str(idx.date() if hasattr(idx, "date") else idx), "value": float(v)}
        for idx, v in data["value"].items()
        if v == v  # exclude NaN
    ][:60]
