"""
MCP tools for equity market data.

Sources (with fallback order):
  Quotes / prices : yfinance → tiingo
  Fundamentals    : yfinance → polygon (reference data)
  Options         : yfinance (only source)
  News            : tiingo → yfinance
  Financial stmts : SEC EDGAR XBRL (authoritative)
  Insider trades  : SEC EDGAR Form 4
"""

from __future__ import annotations

import json
import logging
from typing import Any

from financial_mcp.exceptions import FinancialMCPError, MissingAPIKeyError

logger = logging.getLogger(__name__)


def _try_sources(primary_fn, fallback_fn=None, *args, **kwargs) -> Any:
    """Attempt primary, fall back to secondary on any error."""
    try:
        return primary_fn(*args, **kwargs)
    except MissingAPIKeyError:
        raise  # Don't swallow key errors — surface them to the user
    except FinancialMCPError as exc:
        if fallback_fn is None:
            raise
        logger.warning("Primary source failed (%s), trying fallback", exc)
        return fallback_fn(*args, **kwargs)
    except Exception as exc:
        if fallback_fn is None:
            raise FinancialMCPError(str(exc)) from exc
        logger.warning("Primary source raised unexpected error (%s), trying fallback", exc)
        return fallback_fn(*args, **kwargs)


def _error_response(tool_name: str, exc: Exception) -> str:
    return json.dumps({
        "error":   type(exc).__name__,
        "message": str(exc),
        "tool":    tool_name,
    }, indent=2)


# ── get_stock_quote ────────────────────────────────────────────────────────────

def get_stock_quote(ticker: str) -> str:
    """
    Get a real-time (15-min delayed) price quote for a stock or ETF.

    Args:
        ticker: Stock ticker symbol, e.g. "AAPL", "MSFT", "SPY".

    Returns JSON with: symbol, name, price, open, high, low, volume,
    previous_close, change, change_pct, market_cap, currency, exchange.
    """
    try:
        from financial_mcp.adapters import yfinance_adapter as yf
        result = yf.get_quote(ticker)
        return json.dumps(result, indent=2)
    except Exception as exc:
        return _error_response("get_stock_quote", exc)


# ── get_price_history ──────────────────────────────────────────────────────────

def get_price_history(
    ticker: str,
    period: str = "1y",
    interval: str = "1d",
    source: str = "auto",
) -> str:
    """
    Get historical OHLCV price data for a stock or ETF.

    Args:
        ticker:   Stock ticker symbol, e.g. "AAPL".
        period:   Time period — "1d","5d","1mo","3mo","6mo","1y","2y","5y","10y","ytd","max".
                  Ignored if start_date/end_date are used.
        interval: Bar interval — "1d" (daily), "1wk" (weekly), "1mo" (monthly),
                  or intraday "1m","5m","15m","30m","1h" (max 60 days back for intraday).
        source:   "auto" (yfinance → tiingo fallback), "yfinance", or "tiingo".

    Returns a JSON array of OHLCV bars sorted oldest-first.
    """
    try:
        if source == "tiingo":
            from financial_mcp.adapters import tiingo_adapter as ti
            result = ti.get_price_history(ticker)
        elif source == "yfinance":
            from financial_mcp.adapters import yfinance_adapter as yf
            result = yf.get_price_history(ticker, period=period, interval=interval)
        else:
            # auto: yfinance first, tiingo fallback
            try:
                from financial_mcp.adapters import yfinance_adapter as yf
                result = yf.get_price_history(ticker, period=period, interval=interval)
            except Exception as exc:
                logger.warning("yfinance price history failed for %s: %s — trying tiingo", ticker, exc)
                from financial_mcp.adapters import tiingo_adapter as ti
                result = ti.get_price_history(ticker)
        return json.dumps(result, indent=2)
    except Exception as exc:
        return _error_response("get_price_history", exc)


# ── get_options_chain ──────────────────────────────────────────────────────────

def get_options_chain(ticker: str, expiration: str | None = None) -> str:
    """
    Get the options chain (calls and puts) for a stock.

    Args:
        ticker:     Stock ticker symbol, e.g. "AAPL".
        expiration: Optional expiration date string "YYYY-MM-DD".
                    If omitted, the nearest expiration is returned.

    Returns JSON with expiration date, available_expirations, calls[], puts[].
    Each contract includes: strike, lastPrice, bid, ask, volume, openInterest,
    impliedVolatility, inTheMoney.
    """
    try:
        from financial_mcp.adapters import yfinance_adapter as yf
        result = yf.get_options_chain(ticker, expiration=expiration)
        return json.dumps(result, indent=2, default=str)
    except Exception as exc:
        return _error_response("get_options_chain", exc)


# ── get_fundamentals ───────────────────────────────────────────────────────────

def get_fundamentals(ticker: str) -> str:
    """
    Get key fundamental metrics for a stock.

    Includes: valuation (P/E, P/B, P/S, EV/EBITDA), profitability margins,
    return ratios (ROE, ROA), growth rates, balance sheet summary, dividends,
    analyst recommendations, and share statistics.

    Args:
        ticker: Stock ticker symbol, e.g. "AAPL".
    """
    try:
        from financial_mcp.adapters import yfinance_adapter as yf
        result = yf.get_fundamentals(ticker)
        return json.dumps(result, indent=2, default=str)
    except Exception as exc:
        return _error_response("get_fundamentals", exc)


# ── get_financial_statements ───────────────────────────────────────────────────

def get_financial_statements(ticker: str) -> str:
    """
    Get structured annual financial statements from SEC EDGAR XBRL.

    Data is sourced directly from the official SEC EDGAR XBRL API — the same
    data companies file with the SEC.  Covers up to 10 fiscal years.

    Returns income statement, balance sheet, and cash flow statement data,
    each as a dict of {concept_name: [{period_end, value, unit, accession}]}.

    Args:
        ticker: US stock ticker symbol, e.g. "AAPL". Company must be SEC-registered.
    """
    try:
        from financial_mcp.adapters import sec_adapter
        result = sec_adapter.get_financial_statements(ticker)
        return json.dumps(result, indent=2)
    except Exception as exc:
        return _error_response("get_financial_statements", exc)


# ── get_sec_filings ────────────────────────────────────────────────────────────

def get_sec_filings(ticker: str, form_type: str = "10-K", limit: int = 5) -> str:
    """
    Get recent SEC filings for a company with links to the actual documents.

    Args:
        ticker:    US stock ticker symbol, e.g. "AAPL".
        form_type: SEC form type — "10-K" (annual), "10-Q" (quarterly),
                   "8-K" (current events), "DEF 14A" (proxy), "4" (insider trades).
        limit:     Max number of filings to return (default 5, max 20).
    """
    try:
        from financial_mcp.adapters import sec_adapter
        result = sec_adapter.get_filings(ticker, form_type=form_type, limit=min(limit, 20))
        return json.dumps(result, indent=2)
    except Exception as exc:
        return _error_response("get_sec_filings", exc)


# ── get_insider_transactions ───────────────────────────────────────────────────

def get_insider_transactions(ticker: str, limit: int = 20) -> str:
    """
    Get recent insider transaction filings (Form 4) for a company.

    Form 4 filings are submitted whenever a company insider (officer, director,
    or 10%+ shareholder) buys or sells company stock.

    Args:
        ticker: US stock ticker symbol, e.g. "AAPL".
        limit:  Max number of Form 4 filings to return.
    """
    try:
        from financial_mcp.adapters import sec_adapter
        result = sec_adapter.get_insider_transactions(ticker, limit=limit)
        return json.dumps(result, indent=2)
    except Exception as exc:
        return _error_response("get_insider_transactions", exc)


# ── get_stock_news ─────────────────────────────────────────────────────────────

def get_stock_news(ticker: str, limit: int = 10) -> str:
    """
    Get recent news articles for a stock ticker.

    Tries Tiingo first (superior article metadata + topic tags), falls back
    to yfinance if Tiingo key is unavailable.

    Args:
        ticker: Stock ticker symbol, e.g. "AAPL".
        limit:  Max articles to return (default 10).
    """
    try:
        try:
            from financial_mcp.adapters import tiingo_adapter as ti
            result = ti.get_news(tickers=[ticker], limit=limit)
            return json.dumps(result, indent=2)
        except MissingAPIKeyError:
            from financial_mcp.adapters import yfinance_adapter as yf
            result = yf.get_news(ticker, max_items=limit)
            return json.dumps(result, indent=2)
    except Exception as exc:
        return _error_response("get_stock_news", exc)


# ── get_ticker_details ─────────────────────────────────────────────────────────

def get_ticker_details(ticker: str) -> str:
    """
    Get company profile and reference data for a stock.

    Includes: company name, sector, industry, description, website,
    employee count, listing date, and exchange.

    Args:
        ticker: Stock ticker symbol, e.g. "AAPL".
    """
    try:
        try:
            from financial_mcp.adapters import polygon_adapter
            result = polygon_adapter.get_ticker_details(ticker)
            return json.dumps(result, indent=2)
        except MissingAPIKeyError:
            from financial_mcp.adapters import yfinance_adapter as yf
            info = yf.get_fundamentals(ticker)
            # Shape into a similar profile response
            result = {
                "symbol":      ticker.upper(),
                "name":        info.get("longName"),
                "sector":      info.get("sector"),
                "industry":    info.get("industry"),
                "country":     info.get("country"),
                "website":     info.get("website"),
                "employees":   info.get("fullTimeEmployees"),
                "source":      "yfinance",
            }
            return json.dumps(result, indent=2)
    except Exception as exc:
        return _error_response("get_ticker_details", exc)
