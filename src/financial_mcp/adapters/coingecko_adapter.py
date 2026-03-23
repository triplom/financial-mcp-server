"""
CoinGecko adapter — Tier 1 crypto data source.

Covers: prices, market caps, 24h volume, historical prices, coin metadata,
trending coins, global crypto market overview, and exchange rates.

Uses pycoingecko.  Demo API key recommended (30 req/min) but not required.
"""

from __future__ import annotations

import logging
from typing import Any

from pycoingecko import CoinGeckoAPI

from financial_mcp.cache import cached
from financial_mcp.config import CONFIG
from financial_mcp.exceptions import DataParseError, SourceUnavailableError, TickerNotFoundError
from financial_mcp.rate_limiter import acquire

logger = logging.getLogger(__name__)

_SOURCE = "coingecko"


def _client() -> CoinGeckoAPI:
    cg = CoinGeckoAPI()
    if CONFIG.keys.has("coingecko"):
        cg.api_key = CONFIG.keys.coingecko
    return cg


# ── Coin ID resolution ─────────────────────────────────────────────────────────

@cached("crypto")
def _coin_list() -> list[dict]:
    """Fetch and cache the full CoinGecko coin list (id / symbol / name)."""
    acquire(_SOURCE)
    try:
        return _client().get_coins_list()
    except Exception as exc:
        raise SourceUnavailableError(_SOURCE, str(exc)) from exc


def resolve_coin_id(symbol_or_id: str) -> str:
    """
    Resolve a ticker symbol (e.g. "BTC") or CoinGecko slug (e.g. "bitcoin")
    to the canonical CoinGecko coin ID.

    If symbol is ambiguous (e.g. "ETH" matches multiple tokens) the most
    prominent match (bitcoin > ethereum > …) is returned via position in list.
    """
    target = symbol_or_id.lower()
    # Direct ID match is fastest
    coins = _coin_list()
    for coin in coins:
        if coin["id"] == target:
            return target
    # Symbol match — return the first (usually most prominent) hit
    for coin in coins:
        if coin["symbol"].lower() == target:
            return coin["id"]
    raise TickerNotFoundError(symbol_or_id, _SOURCE)


# ── Current price / market data ────────────────────────────────────────────────

@cached("crypto")
def get_crypto_price(
    coin: str,
    vs_currency: str = "usd",
) -> dict[str, Any]:
    """
    Return current price and market data for a single coin.

    *coin* can be a symbol (BTC), CoinGecko slug (bitcoin), or coin ID.
    """
    coin_id = resolve_coin_id(coin)
    acquire(_SOURCE)
    try:
        data = _client().get_coin_by_id(
            coin_id,
            localization=False,
            tickers=False,
            community_data=False,
            developer_data=False,
        )
    except Exception as exc:
        raise SourceUnavailableError(_SOURCE, str(exc)) from exc

    md = data.get("market_data", {})
    cur = vs_currency.lower()

    def _get(key: str) -> Any:
        val = md.get(key, {})
        return val.get(cur) if isinstance(val, dict) else val

    return {
        "coin_id":           coin_id,
        "symbol":            data.get("symbol", "").upper(),
        "name":              data.get("name"),
        "price":             _get("current_price"),
        "market_cap":        _get("market_cap"),
        "market_cap_rank":   md.get("market_cap_rank"),
        "fully_diluted_valuation": _get("fully_diluted_valuation"),
        "volume_24h":        _get("total_volume"),
        "high_24h":          _get("high_24h"),
        "low_24h":           _get("low_24h"),
        "change_24h":        _get("price_change_24h"),
        "change_pct_24h":    _get("price_change_percentage_24h"),
        "change_pct_7d":     md.get("price_change_percentage_7d"),
        "change_pct_30d":    md.get("price_change_percentage_30d"),
        "ath":               _get("ath"),
        "ath_date":          md.get("ath_date", {}).get(cur),
        "atl":               _get("atl"),
        "atl_date":          md.get("atl_date", {}).get(cur),
        "circulating_supply": md.get("circulating_supply"),
        "total_supply":      md.get("total_supply"),
        "max_supply":        md.get("max_supply"),
        "vs_currency":       cur,
        "last_updated":      data.get("last_updated"),
        "source":            _SOURCE,
    }


# ── Simple price for multiple coins ───────────────────────────────────────────

@cached("crypto")
def get_prices(
    coins: list[str],
    vs_currencies: list[str] | None = None,
) -> dict[str, Any]:
    """
    Return prices for multiple coins in one API call.

    *coins* can be a mix of symbols and CoinGecko IDs.
    """
    if vs_currencies is None:
        vs_currencies = ["usd"]
    coin_ids = [resolve_coin_id(c) for c in coins]
    acquire(_SOURCE)
    try:
        result = _client().get_price(
            ids=coin_ids,
            vs_currencies=vs_currencies,
            include_market_cap=True,
            include_24hr_vol=True,
            include_24hr_change=True,
        )
    except Exception as exc:
        raise SourceUnavailableError(_SOURCE, str(exc)) from exc
    result["source"] = _SOURCE
    return result


# ── Historical OHLC ────────────────────────────────────────────────────────────

@cached("eod_prices")
def get_crypto_history(
    coin: str,
    vs_currency: str = "usd",
    days: int | str = 30,
) -> dict[str, Any]:
    """
    Return daily OHLC history for *coin*.

    days: integer or "max"
    """
    coin_id = resolve_coin_id(coin)
    acquire(_SOURCE)
    try:
        raw = _client().get_coin_ohlc_by_id(coin_id, vs_currency=vs_currency, days=days)
    except Exception as exc:
        raise SourceUnavailableError(_SOURCE, str(exc)) from exc

    # raw is a list of [timestamp_ms, open, high, low, close]
    bars = [
        {
            "timestamp_ms": row[0],
            "open":  row[1],
            "high":  row[2],
            "low":   row[3],
            "close": row[4],
        }
        for row in (raw or [])
    ]
    return {
        "coin_id":     coin_id,
        "vs_currency": vs_currency,
        "days":        days,
        "ohlc":        bars,
        "source":      _SOURCE,
    }


# ── Global market overview ─────────────────────────────────────────────────────

@cached("crypto")
def get_crypto_market_overview() -> dict[str, Any]:
    """Return global crypto market stats: total market cap, BTC dominance, etc."""
    acquire(_SOURCE)
    try:
        data = _client().get_global()
    except Exception as exc:
        raise SourceUnavailableError(_SOURCE, str(exc)) from exc

    d = data.get("data", data)
    return {
        "total_market_cap_usd":       d.get("total_market_cap", {}).get("usd"),
        "total_volume_24h_usd":       d.get("total_volume", {}).get("usd"),
        "btc_dominance_pct":          d.get("market_cap_percentage", {}).get("btc"),
        "eth_dominance_pct":          d.get("market_cap_percentage", {}).get("eth"),
        "active_cryptocurrencies":    d.get("active_cryptocurrencies"),
        "ongoing_icos":               d.get("ongoing_icos"),
        "market_cap_change_pct_24h":  d.get("market_cap_change_percentage_24h_usd"),
        "updated_at":                 d.get("updated_at"),
        "source":                     _SOURCE,
    }


# ── Trending coins ─────────────────────────────────────────────────────────────

@cached("crypto")
def get_trending_coins() -> list[dict[str, Any]]:
    """Return the top-7 trending coins on CoinGecko in the last 24 hours."""
    acquire(_SOURCE)
    try:
        data = _client().get_search_trending()
    except Exception as exc:
        raise SourceUnavailableError(_SOURCE, str(exc)) from exc

    coins = data.get("coins", [])
    return [
        {
            "rank":      c["item"].get("score", idx) + 1,
            "coin_id":   c["item"].get("id"),
            "name":      c["item"].get("name"),
            "symbol":    c["item"].get("symbol", "").upper(),
            "market_cap_rank": c["item"].get("market_cap_rank"),
            "price_btc": c["item"].get("price_btc"),
        }
        for idx, c in enumerate(coins)
    ]
