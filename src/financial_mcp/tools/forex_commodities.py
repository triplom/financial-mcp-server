"""
MCP tools for forex and commodity data.
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


# ── get_forex_rate ─────────────────────────────────────────────────────────────

def get_forex_rate(base_currency: str, quote_currency: str = "USD") -> str:
    """
    Get the current spot exchange rate between two currencies.

    Tries Polygon.io first (if key is available, more accurate), falls back
    to yfinance for all major currency pairs.

    Args:
        base_currency:  The currency to price (e.g. "EUR", "GBP", "JPY").
        quote_currency: The pricing currency (default "USD").

    Supports all major and most minor FX pairs.  Examples:
      get_forex_rate("EUR")         → EUR/USD rate
      get_forex_rate("GBP", "EUR")  → GBP/EUR cross rate
      get_forex_rate("USD", "JPY")  → USD/JPY rate

    Returns JSON with: pair, rate, source.
    """
    try:
        try:
            from financial_mcp.adapters import polygon_adapter
            result = polygon_adapter.get_forex_snapshot(base_currency, quote_currency)
            return json.dumps(result, indent=2)
        except Exception:
            from financial_mcp.adapters import yfinance_adapter as yf
            result = yf.get_forex_rate(base_currency, quote_currency)
            return json.dumps(result, indent=2)
    except Exception as exc:
        return _error_response("get_forex_rate", exc)


# ── get_commodity_price ────────────────────────────────────────────────────────

def get_commodity_price(commodity: str, interval: str = "monthly") -> str:
    """
    Get historical price data for a commodity.

    Powered by Alpha Vantage (requires ALPHA_VANTAGE_API_KEY).
    Falls back to yfinance futures prices if Alpha Vantage is unavailable.

    Supported commodities:
      Energy    : "wti" (WTI crude oil), "brent" (Brent crude), "natural_gas"
      Metals    : "copper", "aluminum"
      Agriculture: "wheat", "corn", "cotton", "sugar", "coffee"

    Args:
        commodity: Commodity name from the list above.
        interval:  "daily" | "weekly" | "monthly" (default "monthly").

    Returns JSON array of {date, value} observations.
    """
    try:
        # Try Alpha Vantage first (authoritative commodity series)
        from financial_mcp.exceptions import MissingAPIKeyError
        try:
            from financial_mcp.adapters import alpha_vantage_adapter as av
            result = av.get_commodity_price(commodity, interval=interval)
            return json.dumps({"commodity": commodity, "interval": interval,
                                "data": result, "source": "alpha_vantage"}, indent=2)
        except (MissingAPIKeyError, ValueError):
            # Fallback: yfinance futures tickers
            _yf_futures = {
                "wti":         "CL=F",
                "brent":       "BZ=F",
                "natural_gas": "NG=F",
                "gold":        "GC=F",
                "silver":      "SI=F",
                "copper":      "HG=F",
                "corn":        "ZC=F",
                "wheat":       "ZW=F",
                "soy":         "ZS=F",
            }
            yf_ticker = _yf_futures.get(commodity.lower())
            if not yf_ticker:
                raise ValueError(
                    f"Commodity '{commodity}' not available via yfinance fallback. "
                    f"Set ALPHA_VANTAGE_API_KEY for full commodity support."
                )
            from financial_mcp.adapters import yfinance_adapter as yf
            history = yf.get_price_history(yf_ticker, period="2y", interval="1mo")
            result = [{"date": bar["date"][:10], "value": bar["close"]} for bar in history]
            return json.dumps({
                "commodity": commodity,
                "interval":  "monthly",
                "data":      result,
                "source":    "yfinance_futures",
                "note":      f"Futures contract {yf_ticker}. Set ALPHA_VANTAGE_API_KEY for spot prices.",
            }, indent=2)
    except Exception as exc:
        return _error_response("get_commodity_price", exc)


# ── get_technical_indicators ───────────────────────────────────────────────────

def get_technical_indicators(
    ticker: str,
    indicators: str = "rsi,macd,bbands",
    interval: str = "daily",
) -> str:
    """
    Get technical analysis indicators for a stock.

    Powered by Alpha Vantage (requires ALPHA_VANTAGE_API_KEY).
    WARNING: Free tier is 25 requests/day — each indicator uses one request.

    Supported indicators (comma-separated):
      "rsi"    → Relative Strength Index (14-period)
      "macd"   → MACD, Signal, Histogram (12/26/9)
      "bbands" → Bollinger Bands (20-period, 2 std dev)
      "sma_50" → 50-day Simple Moving Average
      "sma_200"→ 200-day Simple Moving Average

    Args:
        ticker:     Stock ticker symbol, e.g. "AAPL".
        indicators: Comma-separated list of indicators (default "rsi,macd,bbands").
        interval:   Bar interval — "daily" | "weekly" | "monthly".

    Returns JSON with each requested indicator as a key containing recent values.
    """
    try:
        from financial_mcp.adapters import alpha_vantage_adapter as av
        requested = [i.strip().lower() for i in indicators.split(",")]
        result: dict = {"ticker": ticker.upper(), "interval": interval, "source": "alpha_vantage"}

        for ind in requested:
            try:
                if ind == "rsi":
                    result["rsi"] = av.get_rsi(ticker, interval=interval)
                elif ind == "macd":
                    result["macd"] = av.get_macd(ticker, interval=interval)
                elif ind == "bbands":
                    result["bbands"] = av.get_bbands(ticker, interval=interval)
                elif ind == "sma_50":
                    result["sma_50"] = av.get_sma(ticker, interval=interval, time_period=50)
                elif ind == "sma_200":
                    result["sma_200"] = av.get_sma(ticker, interval=interval, time_period=200)
                else:
                    result[ind] = {"error": f"Unknown indicator '{ind}'"}
            except Exception as exc:
                result[ind] = {"error": str(exc)}

        return json.dumps(result, indent=2)
    except Exception as exc:
        return _error_response("get_technical_indicators", exc)
