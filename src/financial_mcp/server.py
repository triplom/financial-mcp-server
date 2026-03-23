"""
Financial MCP Server — entry point.

Registers all financial data tools with the MCP framework and starts the
server in stdio mode (standard for MCP integrations with Claude Desktop,
Cursor, VS Code, etc.).
"""

from __future__ import annotations

import json
import logging
from typing import Any

import mcp.server.stdio
import mcp.types as types
from mcp.server import Server
from mcp.server.models import InitializationOptions

from financial_mcp.cache import stats as cache_stats
from financial_mcp.config import CONFIG

logger = logging.getLogger(__name__)

# ── Instantiate server ─────────────────────────────────────────────────────────

app = Server("financial-mcp-server")

# ── Tool registry ──────────────────────────────────────────────────────────────
# Each entry: (tool_name, description, input_schema, handler_fn)
# handler_fn receives **kwargs matching the schema properties.

_TOOLS: list[tuple[str, str, dict, Any]] = []


def _register(name: str, description: str, schema: dict):
    """Decorator that registers a function as an MCP tool."""
    def decorator(fn):
        _TOOLS.append((name, description, schema, fn))
        return fn
    return decorator


# ── Import tool functions ──────────────────────────────────────────────────────

from financial_mcp.tools.equities import (
    get_stock_quote,
    get_price_history,
    get_options_chain,
    get_fundamentals,
    get_financial_statements,
    get_sec_filings,
    get_insider_transactions,
    get_stock_news,
    get_ticker_details,
)
from financial_mcp.tools.macro import (
    get_macro_series,
    get_yield_curve,
    get_inflation_snapshot,
    search_fred_series,
    list_well_known_fred_series,
)
from financial_mcp.tools.crypto import (
    get_crypto_price,
    get_crypto_prices,
    get_crypto_history,
    get_crypto_market_overview,
    get_trending_crypto,
    get_crypto_news,
)
from financial_mcp.tools.forex_commodities import (
    get_forex_rate,
    get_commodity_price,
    get_technical_indicators,
)


# ── Tool definitions ───────────────────────────────────────────────────────────

_TOOL_DEFS: list[tuple[str, Any, dict]] = [

    # ── Equities ────────────────────────────────────────────────────────────────
    ("get_stock_quote", get_stock_quote, {
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "Stock ticker symbol (e.g. AAPL, MSFT, SPY)"},
        },
        "required": ["ticker"],
    }),

    ("get_price_history", get_price_history, {
        "type": "object",
        "properties": {
            "ticker":   {"type": "string", "description": "Stock ticker symbol"},
            "period":   {"type": "string", "description": "Time period: 1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,ytd,max", "default": "1y"},
            "interval": {"type": "string", "description": "Bar interval: 1d,1wk,1mo or intraday 1m,5m,15m,30m,1h", "default": "1d"},
            "source":   {"type": "string", "description": "Data source: auto, yfinance, or tiingo", "default": "auto"},
        },
        "required": ["ticker"],
    }),

    ("get_options_chain", get_options_chain, {
        "type": "object",
        "properties": {
            "ticker":     {"type": "string", "description": "Stock ticker symbol"},
            "expiration": {"type": "string", "description": "Expiration date YYYY-MM-DD (optional, defaults to nearest)"},
        },
        "required": ["ticker"],
    }),

    ("get_fundamentals", get_fundamentals, {
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "Stock ticker symbol"},
        },
        "required": ["ticker"],
    }),

    ("get_financial_statements", get_financial_statements, {
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "US stock ticker symbol (company must file with SEC)"},
        },
        "required": ["ticker"],
    }),

    ("get_sec_filings", get_sec_filings, {
        "type": "object",
        "properties": {
            "ticker":    {"type": "string", "description": "US stock ticker symbol"},
            "form_type": {"type": "string", "description": "SEC form type: 10-K, 10-Q, 8-K, DEF 14A, 4", "default": "10-K"},
            "limit":     {"type": "integer", "description": "Max number of filings to return (default 5)", "default": 5},
        },
        "required": ["ticker"],
    }),

    ("get_insider_transactions", get_insider_transactions, {
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "US stock ticker symbol"},
            "limit":  {"type": "integer", "description": "Max Form 4 filings to return", "default": 20},
        },
        "required": ["ticker"],
    }),

    ("get_stock_news", get_stock_news, {
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "Stock ticker symbol"},
            "limit":  {"type": "integer", "description": "Max articles to return (default 10)", "default": 10},
        },
        "required": ["ticker"],
    }),

    ("get_ticker_details", get_ticker_details, {
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "Stock ticker symbol"},
        },
        "required": ["ticker"],
    }),

    # ── Macroeconomics ──────────────────────────────────────────────────────────
    ("get_macro_series", get_macro_series, {
        "type": "object",
        "properties": {
            "series_id":  {"type": "string", "description": "FRED series ID or alias (e.g. cpi, gdp, unemployment, 10y_treasury)"},
            "start_date": {"type": "string", "description": "Start date YYYY-MM-DD (optional)"},
            "end_date":   {"type": "string", "description": "End date YYYY-MM-DD (optional)"},
            "limit":      {"type": "integer", "description": "Max observations to return (default 100)", "default": 100},
        },
        "required": ["series_id"],
    }),

    ("get_yield_curve", get_yield_curve, {
        "type": "object",
        "properties": {},
    }),

    ("get_inflation_snapshot", get_inflation_snapshot, {
        "type": "object",
        "properties": {},
    }),

    ("search_fred_series", search_fred_series, {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query, e.g. 'housing starts', 'PCE deflator'"},
            "limit": {"type": "integer", "description": "Max results (default 10)", "default": 10},
        },
        "required": ["query"],
    }),

    ("list_well_known_fred_series", list_well_known_fred_series, {
        "type": "object",
        "properties": {},
    }),

    # ── Crypto ──────────────────────────────────────────────────────────────────
    ("get_crypto_price", get_crypto_price, {
        "type": "object",
        "properties": {
            "coin":        {"type": "string", "description": "Coin symbol (BTC, ETH, SOL) or CoinGecko slug (bitcoin, ethereum)"},
            "vs_currency": {"type": "string", "description": "Quote currency (default usd)", "default": "usd"},
        },
        "required": ["coin"],
    }),

    ("get_crypto_prices", get_crypto_prices, {
        "type": "object",
        "properties": {
            "coins":         {"type": "string", "description": "Comma-separated coin symbols, e.g. BTC,ETH,SOL"},
            "vs_currencies": {"type": "string", "description": "Comma-separated quote currencies, e.g. usd,eur", "default": "usd"},
        },
        "required": ["coins"],
    }),

    ("get_crypto_history", get_crypto_history, {
        "type": "object",
        "properties": {
            "coin":        {"type": "string", "description": "Coin symbol or CoinGecko slug"},
            "vs_currency": {"type": "string", "description": "Quote currency (default usd)", "default": "usd"},
            "days":        {"type": "integer", "description": "Days of history: 1,7,14,30,90,180,365", "default": 30},
        },
        "required": ["coin"],
    }),

    ("get_crypto_market_overview", get_crypto_market_overview, {
        "type": "object",
        "properties": {},
    }),

    ("get_trending_crypto", get_trending_crypto, {
        "type": "object",
        "properties": {},
    }),

    ("get_crypto_news", get_crypto_news, {
        "type": "object",
        "properties": {
            "coin_symbol": {"type": "string", "description": "Crypto ticker to filter by (e.g. BTC). Omit for general crypto news."},
            "limit":       {"type": "integer", "description": "Max articles (default 10)", "default": 10},
        },
    }),

    # ── Forex & Commodities ─────────────────────────────────────────────────────
    ("get_forex_rate", get_forex_rate, {
        "type": "object",
        "properties": {
            "base_currency":  {"type": "string", "description": "Base currency code (e.g. EUR, GBP, JPY)"},
            "quote_currency": {"type": "string", "description": "Quote currency code (default USD)", "default": "USD"},
        },
        "required": ["base_currency"],
    }),

    ("get_commodity_price", get_commodity_price, {
        "type": "object",
        "properties": {
            "commodity": {"type": "string", "description": "Commodity: wti, brent, natural_gas, gold, silver, copper, wheat, corn, soy, sugar, coffee, cotton, aluminum"},
            "interval":  {"type": "string", "description": "Interval: daily, weekly, monthly (default monthly)", "default": "monthly"},
        },
        "required": ["commodity"],
    }),

    ("get_technical_indicators", get_technical_indicators, {
        "type": "object",
        "properties": {
            "ticker":     {"type": "string", "description": "Stock ticker symbol"},
            "indicators": {"type": "string", "description": "Comma-separated: rsi, macd, bbands, sma_50, sma_200", "default": "rsi,macd,bbands"},
            "interval":   {"type": "string", "description": "Bar interval: daily, weekly, monthly", "default": "daily"},
        },
        "required": ["ticker"],
    }),

    # ── Diagnostics ─────────────────────────────────────────────────────────────
    ("get_server_status", None, {
        "type": "object",
        "properties": {},
    }),
]


# ── MCP handler implementations ────────────────────────────────────────────────

@app.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """Return the full list of available MCP tools."""
    tools = []
    for name, _fn, schema in _TOOL_DEFS:
        # Build description from the function docstring (first line)
        if _fn is not None:
            desc = (_fn.__doc__ or "").strip().split("\n")[0]
        else:
            desc = "Get server status, available sources, and cache statistics."
        tools.append(types.Tool(
            name=name,
            description=desc,
            inputSchema=schema,
        ))
    return tools


@app.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent]:
    """Dispatch a tool call to the correct handler function."""
    kwargs = arguments or {}

    # Special case: server status (no adapter needed)
    if name == "get_server_status":
        status = {
            "server":  "financial-mcp-server",
            "version": "0.1.0",
            "sources": {
                "yfinance":      {"status": "always_available", "key_required": False},
                "fred":          {"status": "available" if CONFIG.keys.has("fred") else "key_missing", "key_required": True},
                "sec_edgar":     {"status": "always_available", "key_required": False},
                "coingecko":     {"status": "available", "key_required": False, "demo_key": CONFIG.keys.has("coingecko")},
                "tiingo":        {"status": "available" if CONFIG.keys.has("tiingo") else "key_missing", "key_required": True},
                "polygon":       {"status": "available" if CONFIG.keys.has("polygon") else "key_missing", "key_required": True},
                "alpha_vantage": {"status": "available" if CONFIG.keys.has("alpha_vantage") else "key_missing", "key_required": True},
            },
            "cache":   cache_stats(),
        }
        return [types.TextContent(type="text", text=json.dumps(status, indent=2))]

    # Dispatch to the matching tool function
    fn = None
    for tool_name, tool_fn, _schema in _TOOL_DEFS:
        if tool_name == name:
            fn = tool_fn
            break

    if fn is None:
        error = json.dumps({"error": "ToolNotFound", "message": f"No tool named '{name}'"})
        return [types.TextContent(type="text", text=error)]

    try:
        result = fn(**kwargs)
        return [types.TextContent(type="text", text=result)]
    except Exception as exc:
        logger.exception("Unhandled error in tool '%s'", name)
        error = json.dumps({"error": type(exc).__name__, "message": str(exc), "tool": name})
        return [types.TextContent(type="text", text=error)]


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    """Start the MCP server in stdio mode."""
    import asyncio

    logger.info("Starting Financial MCP Server v0.1.0")
    logger.info("Tools available: %d", len(_TOOL_DEFS))

    # Log which optional sources are configured
    for source, key_attr in [
        ("FRED", "fred"), ("Tiingo", "tiingo"),
        ("Polygon", "polygon"), ("Alpha Vantage", "alpha_vantage"),
        ("CoinGecko Demo", "coingecko"),
    ]:
        status = "✓ configured" if CONFIG.keys.has(key_attr) else "✗ key missing (optional)"
        logger.info("  %s: %s", source, status)

    async def _run():
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            init_opts = InitializationOptions(
                server_name="financial-mcp-server",
                server_version="0.1.0",
                capabilities=app.get_capabilities(
                    notification_options=None,
                    experimental_capabilities={},
                ),
            )
            await app.run(read_stream, write_stream, init_opts)

    asyncio.run(_run())


if __name__ == "__main__":
    main()
