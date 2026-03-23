"""
SEC EDGAR adapter — official government financial data, completely free.

Two data paths:
  1. XBRL Company Facts API  → structured financial statements (no key needed)
  2. EDGAR full-text search  → filing metadata & document links

Endpoints used:
  https://data.sec.gov/submissions/{CIK}.json        (filing history)
  https://data.sec.gov/api/xbrl/companyfacts/{CIK}.json  (all XBRL facts)
  https://efts.sec.gov/LATEST/search-index?...        (full-text search)
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from financial_mcp.cache import cached
from financial_mcp.exceptions import DataParseError, SourceUnavailableError, TickerNotFoundError
from financial_mcp.rate_limiter import acquire

logger = logging.getLogger(__name__)

_SOURCE = "sec_edgar"
_HEADERS = {
    "User-Agent": "financial-mcp-server contact@example.com",
    "Accept": "application/json",
}

# Key US-GAAP concepts for financial statements
_INCOME_STMT_CONCEPTS = [
    "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet", "GrossProfit", "OperatingIncomeLoss",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    "IncomeTaxExpenseBenefit", "NetIncomeLoss",
    "EarningsPerShareBasic", "EarningsPerShareDiluted",
    "CommonStockDividendsPerShareDeclared",
]
_BALANCE_SHEET_CONCEPTS = [
    "Assets", "AssetsCurrent", "AssetsNoncurrent",
    "CashAndCashEquivalentsAtCarryingValue",
    "Liabilities", "LiabilitiesCurrent", "LiabilitiesNoncurrent",
    "LongTermDebt", "StockholdersEquity",
    "RetainedEarningsAccumulatedDeficit",
]
_CASHFLOW_CONCEPTS = [
    "NetCashProvidedByUsedInOperatingActivities",
    "NetCashProvidedByUsedInInvestingActivities",
    "NetCashProvidedByUsedInFinancingActivities",
    "CapitalExpenditureDiscontinuedOperations",
    "PaymentsToAcquirePropertyPlantAndEquipment",
]


# ── CIK lookup ─────────────────────────────────────────────────────────────────

@cached("sec_filings")
def get_cik(ticker: str) -> str:
    """Return the zero-padded 10-digit CIK for *ticker*."""
    acquire(_SOURCE)
    url = "https://www.sec.gov/files/company_tickers.json"
    try:
        resp = httpx.get(url, headers=_HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        raise SourceUnavailableError(_SOURCE, str(exc)) from exc

    ticker_upper = ticker.upper()
    for entry in data.values():
        if entry.get("ticker", "").upper() == ticker_upper:
            return str(entry["cik_str"]).zfill(10)
    raise TickerNotFoundError(ticker, _SOURCE)


# ── Submissions / filing history ───────────────────────────────────────────────

@cached("sec_filings")
def get_filings(ticker: str, form_type: str = "10-K", limit: int = 5) -> list[dict[str, Any]]:
    """
    Return recent SEC filings of *form_type* for *ticker*.

    form_type: "10-K", "10-Q", "8-K", "DEF 14A", "4", etc.
    """
    cik = get_cik(ticker)
    acquire(_SOURCE)
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    try:
        resp = httpx.get(url, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
        submissions = resp.json()
    except Exception as exc:
        raise SourceUnavailableError(_SOURCE, str(exc)) from exc

    filings_raw = submissions.get("filings", {}).get("recent", {})
    forms   = filings_raw.get("form", [])
    dates   = filings_raw.get("filingDate", [])
    accnums = filings_raw.get("accessionNumber", [])
    docs    = filings_raw.get("primaryDocument", [])

    results = []
    for form, date, accnum, doc in zip(forms, dates, accnums, docs):
        if form_type and form.upper() != form_type.upper():
            continue
        accnum_clean = accnum.replace("-", "")
        filing_url = (
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
            f"{accnum_clean}/{doc}"
        )
        results.append({
            "form":       form,
            "filed":      date,
            "accession":  accnum,
            "document":   doc,
            "url":        filing_url,
            "ticker":     ticker.upper(),
            "cik":        cik,
        })
        if len(results) >= limit:
            break

    return results


# ── XBRL company facts ─────────────────────────────────────────────────────────

@cached("sec_filings")
def _get_company_facts(cik: str) -> dict[str, Any]:
    """Fetch and cache the full XBRL facts blob for a CIK."""
    acquire(_SOURCE)
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    try:
        resp = httpx.get(url, headers=_HEADERS, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        raise SourceUnavailableError(_SOURCE, str(exc)) from exc


def _extract_concept(facts: dict, concept: str, unit: str = "USD") -> list[dict[str, Any]]:
    """Pull all annual (10-K) values for a US-GAAP concept from the facts blob."""
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    concept_data = us_gaap.get(concept, {})
    units_data = concept_data.get("units", {}).get(unit, [])

    # Keep only annual 10-K filings, deduplicate by fiscal year end
    seen: set[str] = set()
    results = []
    for obs in sorted(units_data, key=lambda x: x.get("end", ""), reverse=True):
        if obs.get("form") != "10-K":
            continue
        end = obs.get("end", "")
        if end in seen:
            continue
        seen.add(end)
        results.append({
            "period_end": end,
            "value":      obs.get("val"),
            "unit":       unit,
            "accession":  obs.get("accn"),
        })
    return results[:10]  # last 10 fiscal years


@cached("fundamentals")
def get_financial_statements(ticker: str) -> dict[str, Any]:
    """
    Return structured annual financial statement data from SEC XBRL.

    Returns income statement, balance sheet, and cash flow concepts
    for up to 10 fiscal years.
    """
    cik = get_cik(ticker)
    facts = _get_company_facts(cik)

    entity_name = facts.get("entityName", ticker.upper())

    def _pull(concepts: list[str], unit: str = "USD") -> dict[str, list]:
        return {c: _extract_concept(facts, c, unit) for c in concepts if _extract_concept(facts, c, unit)}

    income    = _pull(_INCOME_STMT_CONCEPTS)
    balance   = _pull(_BALANCE_SHEET_CONCEPTS)
    cashflow  = _pull(_CASHFLOW_CONCEPTS)

    # EPS uses "USD/shares" unit
    for eps_concept in ("EarningsPerShareBasic", "EarningsPerShareDiluted"):
        eps_data = _extract_concept(facts, eps_concept, "USD/shares")
        if eps_data:
            income[eps_concept] = eps_data

    return {
        "ticker":             ticker.upper(),
        "entity_name":        entity_name,
        "cik":                cik,
        "income_statement":   income,
        "balance_sheet":      balance,
        "cash_flow":          cashflow,
        "source":             _SOURCE,
    }


# ── Insider transactions (Form 4) ──────────────────────────────────────────────

@cached("sec_filings")
def get_insider_transactions(ticker: str, limit: int = 20) -> list[dict[str, Any]]:
    """
    Return recent Form 4 (insider transaction) filings for *ticker*.
    Parses the filing index for basic metadata; full XML parsing is out of scope.
    """
    filings = get_filings(ticker, form_type="4", limit=limit)
    return filings


# ── Full-text search ───────────────────────────────────────────────────────────

def search_filings(query: str, form_type: str = "", limit: int = 10) -> list[dict[str, Any]]:
    """
    Full-text search across EDGAR filings.

    Args:
        query:     Search query string.
        form_type: Optionally filter by form type (e.g. "10-K").
        limit:     Max results to return.
    """
    acquire(_SOURCE)
    params: dict[str, Any] = {
        "q":       f'"{query}"',
        "dateRange": "custom",
        "_source": "file_date,period_of_report,entity_name,file_num,form_type",
        "hits.hits.total.value": 1,
        "hits.hits._source.period_of_report": 1,
        "hits.hits._source.form_type": 1,
    }
    if form_type:
        params["forms"] = form_type

    url = "https://efts.sec.gov/LATEST/search-index"
    try:
        resp = httpx.get(url, params=params, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        raise SourceUnavailableError(_SOURCE, str(exc)) from exc

    hits = data.get("hits", {}).get("hits", [])[:limit]
    results = []
    for hit in hits:
        src = hit.get("_source", {})
        results.append({
            "entity":      src.get("entity_name", ""),
            "form":        src.get("form_type", ""),
            "filed":       src.get("file_date", ""),
            "period":      src.get("period_of_report", ""),
            "edgar_url":   f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&filenum={src.get('file_num', '')}",
        })
    return results
