"""
Centralised configuration loaded from environment variables / .env file.
All other modules import from here — never read os.environ directly.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root (two levels up from this file)
_PROJECT_ROOT = Path(__file__).parent.parent.parent
load_dotenv(_PROJECT_ROOT / ".env", override=False)


def _get(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _get_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (ValueError, TypeError):
        return default


# ── API Keys ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class APIKeys:
    fred: str = field(default_factory=lambda: _get("FRED_API_KEY"))
    alpha_vantage: str = field(default_factory=lambda: _get("ALPHA_VANTAGE_API_KEY"))
    tiingo: str = field(default_factory=lambda: _get("TIINGO_API_KEY"))
    polygon: str = field(default_factory=lambda: _get("POLYGON_API_KEY"))
    coingecko: str = field(default_factory=lambda: _get("COINGECKO_API_KEY"))

    def has(self, name: str) -> bool:
        """Return True if the key exists and is not a placeholder."""
        val = getattr(self, name, "")
        return bool(val) and not val.startswith("your_")


# ── Cache TTLs (seconds) ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class CacheTTLs:
    quotes: int = field(default_factory=lambda: _get_int("CACHE_TTL_QUOTES", 60))
    eod_prices: int = field(default_factory=lambda: _get_int("CACHE_TTL_EOD_PRICES", 86400))
    fundamentals: int = field(default_factory=lambda: _get_int("CACHE_TTL_FUNDAMENTALS", 86400))
    fred: int = field(default_factory=lambda: _get_int("CACHE_TTL_FRED", 86400))
    sec_filings: int = field(default_factory=lambda: _get_int("CACHE_TTL_SEC_FILINGS", 604800))
    news: int = field(default_factory=lambda: _get_int("CACHE_TTL_NEWS", 900))
    crypto: int = field(default_factory=lambda: _get_int("CACHE_TTL_CRYPTO", 120))


# ── Rate limits (min seconds between requests per source) ─────────────────────

@dataclass(frozen=True)
class RateLimits:
    yfinance: float = 1.0          # ~1 req/sec to be polite
    alpha_vantage: float = 12.0    # 25/day free → spread across day; burst buffer here
    polygon: float = 12.0          # 5 req/min free
    tiingo: float = 1.2            # 50 req/hr free
    fred: float = 0.5              # 120 req/60s
    coingecko: float = 2.0         # 30 req/min demo key; more conservative for public
    sec_edgar: float = 0.11        # max 10 req/sec per SEC fair-use guidance


# ── Top-level config singleton ─────────────────────────────────────────────────

@dataclass(frozen=True)
class Config:
    keys: APIKeys = field(default_factory=APIKeys)
    cache: CacheTTLs = field(default_factory=CacheTTLs)
    rate: RateLimits = field(default_factory=RateLimits)
    log_level: str = field(default_factory=lambda: _get("LOG_LEVEL", "INFO"))


CONFIG = Config()

# ── Logging setup ──────────────────────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, CONFIG.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
)
