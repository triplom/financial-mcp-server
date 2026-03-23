"""
FRED adapter — Federal Reserve Economic Data.

Covers macroeconomic series: GDP, CPI, unemployment, interest rates,
yield curve, money supply, housing, and 800 000+ other series.

Requires: FRED_API_KEY in environment.
"""

from __future__ import annotations

import logging
from typing import Any

from fredapi import Fred

from financial_mcp.cache import cached
from financial_mcp.config import CONFIG
from financial_mcp.exceptions import MissingAPIKeyError, SourceUnavailableError
from financial_mcp.rate_limiter import acquire

logger = logging.getLogger(__name__)

_SOURCE = "fred"

# Common series IDs exposed as named helpers
_WELL_KNOWN = {
    "gdp":              "GDP",
    "real_gdp":         "GDPC1",
    "cpi":              "CPIAUCSL",
    "core_cpi":         "CPILFESL",
    "pce":              "PCE",
    "core_pce":         "PCEPILFE",
    "unemployment":     "UNRATE",
    "fed_funds_rate":   "FEDFUNDS",
    "10y_treasury":     "DGS10",
    "2y_treasury":      "DGS2",
    "3m_treasury":      "DGS3MO",
    "30y_mortgage":     "MORTGAGE30US",
    "m2":               "M2SL",
    "industrial_prod":  "INDPRO",
    "retail_sales":     "RSAFS",
    "housing_starts":   "HOUST",
    "nonfarm_payrolls": "PAYEMS",
    "vix":              "VIXCLS",
    "dollar_index":     "DTWEXBGS",
    "wti_crude":        "DCOILWTICO",
    "gold":             "GOLDAMGBD228NLBM",
    "sp500":            "SP500",
}


def _get_client() -> Fred:
    if not CONFIG.keys.has("fred"):
        raise MissingAPIKeyError("FRED", "FRED_API_KEY")
    return Fred(api_key=CONFIG.keys.fred)


def _series_id(series_alias_or_id: str) -> str:
    """Resolve a friendly alias (e.g. 'cpi') or pass through a raw FRED ID."""
    return _WELL_KNOWN.get(series_alias_or_id.lower(), series_alias_or_id.upper())


# ── Core series fetch ──────────────────────────────────────────────────────────

@cached("fred")
def get_series(
    series_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """
    Fetch a FRED data series.

    Args:
        series_id:  FRED series ID or friendly alias (see _WELL_KNOWN).
        start_date: ISO date string "YYYY-MM-DD" (optional).
        end_date:   ISO date string "YYYY-MM-DD" (optional).
        limit:      Max number of observations to return (most recent).

    Returns a dict with series metadata and observations list.
    """
    sid = _series_id(series_id)
    acquire(_SOURCE)
    try:
        client = _get_client()
        # Fetch series info
        info = client.get_series_info(sid)
        # Fetch observations
        kwargs: dict[str, Any] = {}
        if start_date:
            kwargs["observation_start"] = start_date
        if end_date:
            kwargs["observation_end"] = end_date
        data = client.get_series(sid, **kwargs)
    except Exception as exc:
        raise SourceUnavailableError(_SOURCE, str(exc)) from exc

    # Trim to most recent *limit* observations
    if len(data) > limit:
        data = data.iloc[-limit:]

    observations = [
        {"date": str(idx.date()), "value": round(float(v), 6) if v == v else None}
        for idx, v in data.items()
    ]

    return {
        "series_id":   sid,
        "title":       info.get("title", ""),
        "units":       info.get("units", ""),
        "frequency":   info.get("frequency", ""),
        "seasonal_adjustment": info.get("seasonal_adjustment", ""),
        "last_updated": info.get("last_updated", ""),
        "notes":       info.get("notes", ""),
        "observations": observations,
        "source":      _SOURCE,
    }


# ── Yield curve convenience ────────────────────────────────────────────────────

@cached("fred")
def get_yield_curve() -> dict[str, Any]:
    """
    Return the most recent values for the US Treasury yield curve.
    Tenors: 1M, 3M, 6M, 1Y, 2Y, 3Y, 5Y, 7Y, 10Y, 20Y, 30Y.
    """
    tenor_map = {
        "1M":  "DGS1MO",
        "3M":  "DGS3MO",
        "6M":  "DGS6MO",
        "1Y":  "DGS1",
        "2Y":  "DGS2",
        "3Y":  "DGS3",
        "5Y":  "DGS5",
        "7Y":  "DGS7",
        "10Y": "DGS10",
        "20Y": "DGS20",
        "30Y": "DGS30",
    }
    client = _get_client()
    curve: dict[str, float | None] = {}
    date_seen: str | None = None

    for tenor, sid in tenor_map.items():
        acquire(_SOURCE)
        try:
            s = client.get_series(sid)
            s = s.dropna()
            if not s.empty:
                date_seen = str(s.index[-1].date())
                curve[tenor] = round(float(s.iloc[-1]), 4)
            else:
                curve[tenor] = None
        except Exception as exc:
            logger.warning("Yield curve: failed to fetch %s (%s): %s", tenor, sid, exc)
            curve[tenor] = None

    # Compute 10Y–2Y spread (key recession indicator)
    spread = None
    if curve.get("10Y") is not None and curve.get("2Y") is not None:
        spread = round(curve["10Y"] - curve["2Y"], 4)  # type: ignore[operator]

    return {
        "as_of_date":     date_seen,
        "yields":         curve,
        "spread_10y_2y":  spread,
        "inverted":       spread < 0 if spread is not None else None,
        "source":         _SOURCE,
    }


# ── Inflation snapshot ─────────────────────────────────────────────────────────

@cached("fred")
def get_inflation_snapshot() -> dict[str, Any]:
    """Return recent CPI, core CPI, PCE, and core PCE in one call."""
    result: dict[str, Any] = {"source": _SOURCE}
    for label, alias in [
        ("cpi_yoy", "cpi"),
        ("core_cpi_yoy", "core_cpi"),
        ("pce_yoy", "pce"),
        ("core_pce_yoy", "core_pce"),
    ]:
        try:
            series_data = get_series(alias, limit=13)  # 13 months for YoY calc
            obs = series_data["observations"]
            if len(obs) >= 13:
                latest = obs[-1]["value"]
                year_ago = obs[-13]["value"]
                yoy = round((latest - year_ago) / year_ago * 100, 2) if latest and year_ago else None
                result[label] = {
                    "latest_value":  obs[-1]["value"],
                    "latest_date":   obs[-1]["date"],
                    "yoy_change_pct": yoy,
                    "series_id":     series_data["series_id"],
                    "units":         series_data["units"],
                }
            elif obs:
                result[label] = {"latest_value": obs[-1]["value"], "latest_date": obs[-1]["date"]}
        except Exception as exc:
            logger.warning("Inflation snapshot: %s failed: %s", label, exc)
            result[label] = None
    return result


# ── Search ─────────────────────────────────────────────────────────────────────

def search_series(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """
    Search FRED for series matching *query*.
    Results include series_id, title, units, frequency.
    """
    acquire(_SOURCE)
    try:
        client = _get_client()
        results = client.search(query, limit=limit)
    except Exception as exc:
        raise SourceUnavailableError(_SOURCE, str(exc)) from exc

    output = []
    for sid, row in results.iterrows():
        output.append({
            "series_id": sid,
            "title":     row.get("title", ""),
            "units":     row.get("units", ""),
            "frequency": row.get("frequency", ""),
            "seasonal_adjustment": row.get("seasonal_adjustment", ""),
        })
    return output


# ── Alias list ─────────────────────────────────────────────────────────────────

def list_well_known_series() -> dict[str, str]:
    """Return the mapping of friendly alias → FRED series ID."""
    return dict(_WELL_KNOWN)
