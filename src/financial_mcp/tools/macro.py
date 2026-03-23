"""
MCP tools for macroeconomic data via FRED.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _error_response(tool_name: str, exc: Exception) -> str:
    return json.dumps({
        "error":   type(exc).__name__,
        "message": str(exc),
        "tool":    tool_name,
    }, indent=2)


# ── get_macro_series ───────────────────────────────────────────────────────────

def get_macro_series(
    series_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 100,
) -> str:
    """
    Get a macroeconomic data series from FRED (Federal Reserve Economic Data).

    FRED has 800,000+ series covering GDP, inflation, employment, interest rates,
    exchange rates, housing, trade, and more.

    Common series aliases (use instead of raw FRED IDs):
      "gdp"            → Gross Domestic Product (quarterly)
      "real_gdp"       → Real GDP (chained 2017 dollars)
      "cpi"            → CPI for All Urban Consumers
      "core_cpi"       → CPI ex food and energy
      "pce"            → Personal Consumption Expenditures
      "core_pce"       → Core PCE (Fed's preferred inflation gauge)
      "unemployment"   → Civilian Unemployment Rate
      "fed_funds_rate" → Federal Funds Effective Rate
      "10y_treasury"   → 10-Year Treasury Constant Maturity Rate
      "2y_treasury"    → 2-Year Treasury Constant Maturity Rate
      "30y_mortgage"   → 30-Year Fixed Rate Mortgage Average
      "m2"             → M2 Money Supply
      "industrial_prod"→ Industrial Production Index
      "retail_sales"   → Advance Retail Sales
      "housing_starts" → Housing Starts
      "nonfarm_payrolls"→ Total Nonfarm Payrolls
      "vix"            → CBOE Volatility Index
      "sp500"          → S&P 500 Index (daily)
      "wti_crude"      → WTI Crude Oil Price
      "gold"           → Gold Price (London Fix)

    You can also pass any raw FRED series ID (e.g. "GDPC1", "UNRATE").

    Args:
        series_id:  FRED series ID or alias from the list above.
        start_date: Start date "YYYY-MM-DD" (optional).
        end_date:   End date "YYYY-MM-DD" (optional).
        limit:      Max observations to return, most recent first (default 100).

    Returns JSON with: series_id, title, units, frequency, observations[].
    """
    try:
        from financial_mcp.adapters import fred_adapter
        result = fred_adapter.get_series(
            series_id, start_date=start_date, end_date=end_date, limit=limit
        )
        return json.dumps(result, indent=2)
    except Exception as exc:
        return _error_response("get_macro_series", exc)


# ── get_yield_curve ────────────────────────────────────────────────────────────

def get_yield_curve() -> str:
    """
    Get the current US Treasury yield curve.

    Returns yields for 11 tenors (1M through 30Y), the 10Y-2Y spread,
    and whether the curve is currently inverted (a recession indicator).

    No arguments required.

    Returns JSON with: as_of_date, yields{tenor: rate}, spread_10y_2y, inverted.
    """
    try:
        from financial_mcp.adapters import fred_adapter
        result = fred_adapter.get_yield_curve()
        return json.dumps(result, indent=2)
    except Exception as exc:
        return _error_response("get_yield_curve", exc)


# ── get_inflation_snapshot ─────────────────────────────────────────────────────

def get_inflation_snapshot() -> str:
    """
    Get current US inflation data: CPI, Core CPI, PCE, and Core PCE.

    Returns the latest reading and year-over-year percentage change for each
    of the four primary US inflation gauges.  Core PCE is the Fed's preferred
    inflation measure used for monetary policy decisions.

    No arguments required.

    Returns JSON with latest value, date, and YoY % change for each gauge.
    """
    try:
        from financial_mcp.adapters import fred_adapter
        result = fred_adapter.get_inflation_snapshot()
        return json.dumps(result, indent=2)
    except Exception as exc:
        return _error_response("get_inflation_snapshot", exc)


# ── search_fred_series ─────────────────────────────────────────────────────────

def search_fred_series(query: str, limit: int = 10) -> str:
    """
    Search FRED for economic data series matching a query.

    Use this to discover series IDs for obscure or specific economic indicators.
    The returned series_id values can be passed directly to get_macro_series.

    Args:
        query: Natural language search query, e.g. "housing starts", "PCE deflator".
        limit: Max results to return (default 10).

    Returns JSON array of matching series with: series_id, title, units, frequency.
    """
    try:
        from financial_mcp.adapters import fred_adapter
        result = fred_adapter.search_series(query, limit=limit)
        return json.dumps(result, indent=2)
    except Exception as exc:
        return _error_response("search_fred_series", exc)


# ── list_well_known_fred_series ────────────────────────────────────────────────

def list_well_known_fred_series() -> str:
    """
    List all built-in FRED series aliases supported by get_macro_series.

    Returns a JSON object mapping friendly alias → FRED series ID.
    Use these aliases as the series_id parameter in get_macro_series.

    No arguments required.
    """
    try:
        from financial_mcp.adapters import fred_adapter
        result = fred_adapter.list_well_known_series()
        return json.dumps(result, indent=2)
    except Exception as exc:
        return _error_response("list_well_known_fred_series", exc)
