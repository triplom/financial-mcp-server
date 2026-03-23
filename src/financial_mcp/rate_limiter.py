"""
Token-bucket rate limiter — one limiter instance per data source.

Each call to `acquire(source)` blocks (sleeps) until the minimum inter-request
interval for that source has elapsed.  This keeps us well within free-tier
quotas without any external dependency.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

from financial_mcp.config import CONFIG, RateLimits

logger = logging.getLogger(__name__)


@dataclass
class _Limiter:
    min_interval: float          # seconds between requests
    _last_call: float = field(default=0.0, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def acquire(self, source: str = "") -> None:
        with self._lock:
            now = time.monotonic()
            wait = self._min_interval - (now - self._last_call)
            if wait > 0:
                logger.debug("Rate limit: sleeping %.2fs for %s", wait, source)
                time.sleep(wait)
            self._last_call = time.monotonic()

    # Allow the interval to be updated at runtime (e.g. after a 429 response)
    @property
    def min_interval(self) -> float:
        return self._min_interval

    @min_interval.setter
    def min_interval(self, value: float) -> None:
        self._min_interval = value


def _build_limiters(r: RateLimits) -> dict[str, _Limiter]:
    return {
        "yfinance":      _Limiter(r.yfinance),
        "alpha_vantage": _Limiter(r.alpha_vantage),
        "polygon":       _Limiter(r.polygon),
        "tiingo":        _Limiter(r.tiingo),
        "fred":          _Limiter(r.fred),
        "coingecko":     _Limiter(r.coingecko),
        "sec_edgar":     _Limiter(r.sec_edgar),
    }


_LIMITERS: dict[str, _Limiter] = _build_limiters(CONFIG.rate)


def acquire(source: str) -> None:
    """
    Block until it is safe to make the next request to *source*.

    Args:
        source: One of the keys in _LIMITERS (e.g. "yfinance", "fred").
    """
    limiter = _LIMITERS.get(source)
    if limiter is None:
        logger.warning("No rate limiter configured for source '%s' — proceeding unchecked", source)
        return
    limiter.acquire(source)


def backoff(source: str, factor: float = 2.0) -> None:
    """
    Double the rate-limit interval for *source* (called on 429 / quota errors).
    The limiter will naturally slow down subsequent calls.
    """
    limiter = _LIMITERS.get(source)
    if limiter:
        old = limiter.min_interval
        limiter.min_interval = old * factor
        logger.warning(
            "Backing off '%s': interval %.1fs → %.1fs", source, old, limiter.min_interval
        )
