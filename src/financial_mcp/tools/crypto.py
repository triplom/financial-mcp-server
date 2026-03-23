"""
MCP tools for cryptocurrency data.

Sources (with fallback order):
  Prices / market data : CoinGecko → yfinance
  Historical OHLC      : CoinGecko
  Market overview      : CoinGecko
  Trending             : CoinGecko
  News                 : Tiingo (if key available)
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


def _error_response(tool_name: str, exc: Exception) -> str:
    return json.dumps({
        "error":   type(exc).__name__,
        "message": str(exc),
        "tool":    tool_name,
    }, indent=2)


# ── get_crypto_price ───────────────────────────────────────────────────────────

def get_crypto_price(coin: str, vs_currency: str = "usd") -> str:
    """
    Get current price and market data for a cryptocurrency.

    Args:
        coin:        Coin symbol (e.g. "BTC", "ETH", "SOL") or CoinGecko slug
                     (e.g. "bitcoin", "ethereum").  10,000+ coins supported.
        vs_currency: Quote currency (default "usd"). Also supports "eur", "btc",
                     "eth", "gbp", "jpy", and 50+ others.

    Returns JSON with: coin_id, symbol, name, price, market_cap, market_cap_rank,
    volume_24h, high_24h, low_24h, change_pct_24h, change_pct_7d, change_pct_30d,
    ath, atl, circulating_supply, total_supply.
    """
    try:
        from financial_mcp.adapters import coingecko_adapter as cg
        result = cg.get_crypto_price(coin, vs_currency=vs_currency)
        return json.dumps(result, indent=2, default=str)
    except Exception as exc:
        # Fallback: yfinance for major coins
        try:
            symbol = f"{coin.upper()}-{vs_currency.upper()}"
            from financial_mcp.adapters import yfinance_adapter as yf
            result = yf.get_quote(symbol)
            result["note"] = "Served by yfinance fallback (CoinGecko unavailable)"
            return json.dumps(result, indent=2)
        except Exception:
            return _error_response("get_crypto_price", exc)


# ── get_crypto_prices ──────────────────────────────────────────────────────────

def get_crypto_prices(coins: str, vs_currencies: str = "usd") -> str:
    """
    Get prices for multiple cryptocurrencies in one call.

    Args:
        coins:          Comma-separated coin symbols or slugs, e.g. "BTC,ETH,SOL".
        vs_currencies:  Comma-separated quote currencies, e.g. "usd,eur".

    Returns JSON object keyed by CoinGecko ID with prices per currency.
    """
    try:
        coin_list = [c.strip() for c in coins.split(",")]
        currency_list = [c.strip() for c in vs_currencies.split(",")]
        from financial_mcp.adapters import coingecko_adapter as cg
        result = cg.get_prices(coin_list, vs_currencies=currency_list)
        return json.dumps(result, indent=2, default=str)
    except Exception as exc:
        return _error_response("get_crypto_prices", exc)


# ── get_crypto_history ─────────────────────────────────────────────────────────

def get_crypto_history(coin: str, vs_currency: str = "usd", days: int = 30) -> str:
    """
    Get historical OHLC price data for a cryptocurrency.

    Args:
        coin:        Coin symbol or CoinGecko slug, e.g. "BTC" or "bitcoin".
        vs_currency: Quote currency (default "usd").
        days:        Number of days of history (1, 7, 14, 30, 90, 180, 365, or "max").
                     Granularity is automatic: <2 days → 30min, 2–90 days → hourly,
                     >90 days → daily.

    Returns JSON with ohlc[] array of {timestamp_ms, open, high, low, close}.
    """
    try:
        from financial_mcp.adapters import coingecko_adapter as cg
        result = cg.get_crypto_history(coin, vs_currency=vs_currency, days=days)
        return json.dumps(result, indent=2, default=str)
    except Exception as exc:
        return _error_response("get_crypto_history", exc)


# ── get_crypto_market_overview ─────────────────────────────────────────────────

def get_crypto_market_overview() -> str:
    """
    Get a global cryptocurrency market overview.

    Returns: total market cap (USD), 24h volume, BTC dominance %, ETH dominance %,
    number of active cryptocurrencies, and 24h market cap change %.

    No arguments required.
    """
    try:
        from financial_mcp.adapters import coingecko_adapter as cg
        result = cg.get_crypto_market_overview()
        return json.dumps(result, indent=2, default=str)
    except Exception as exc:
        return _error_response("get_crypto_market_overview", exc)


# ── get_trending_crypto ────────────────────────────────────────────────────────

def get_trending_crypto() -> str:
    """
    Get the top trending cryptocurrencies in the last 24 hours.

    Returns the top 7 trending coins on CoinGecko with their rank, name,
    symbol, market cap rank, and price in BTC.

    No arguments required.
    """
    try:
        from financial_mcp.adapters import coingecko_adapter as cg
        result = cg.get_trending_coins()
        return json.dumps(result, indent=2, default=str)
    except Exception as exc:
        return _error_response("get_trending_crypto", exc)


# ── get_crypto_news ────────────────────────────────────────────────────────────

def get_crypto_news(coin_symbol: str | None = None, limit: int = 10) -> str:
    """
    Get recent cryptocurrency news articles.

    Requires a Tiingo API key (TIINGO_API_KEY).  Returns rich article metadata
    including ticker tags, topic tags, publisher, and summary.

    Args:
        coin_symbol: Optional crypto ticker to filter by (e.g. "BTC", "ETH").
                     If omitted, returns general crypto news.
        limit:       Max articles to return (default 10).
    """
    try:
        from financial_mcp.adapters import tiingo_adapter as ti
        tickers = [coin_symbol] if coin_symbol else None
        result = ti.get_news(tickers=tickers, tags=["cryptocurrency"] if not tickers else None, limit=limit)
        return json.dumps(result, indent=2)
    except Exception as exc:
        return _error_response("get_crypto_news", exc)
