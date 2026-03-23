"""
Thread-safe in-memory TTL cache shared across all adapters.

Uses cachetools.TTLCache under the hood.  Each logical data category gets its
own cache bucket so TTLs can differ (e.g. quotes expire in 60 s, SEC filings
in 7 days).
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
import threading
from typing import Any, Callable, TypeVar

from cachetools import TTLCache

from financial_mcp.config import CONFIG

logger = logging.getLogger(__name__)

_lock = threading.Lock()

# One TTLCache per category; maxsize=512 per bucket is generous for a local server
_BUCKETS: dict[str, TTLCache] = {
    "quotes":       TTLCache(maxsize=512, ttl=CONFIG.cache.quotes),
    "eod_prices":   TTLCache(maxsize=256, ttl=CONFIG.cache.eod_prices),
    "fundamentals": TTLCache(maxsize=256, ttl=CONFIG.cache.fundamentals),
    "fred":         TTLCache(maxsize=512, ttl=CONFIG.cache.fred),
    "sec_filings":  TTLCache(maxsize=128, ttl=CONFIG.cache.sec_filings),
    "news":         TTLCache(maxsize=256, ttl=CONFIG.cache.news),
    "crypto":       TTLCache(maxsize=256, ttl=CONFIG.cache.crypto),
}

F = TypeVar("F", bound=Callable[..., Any])


def _make_key(*args: Any, **kwargs: Any) -> str:
    """Stable cache key from positional + keyword arguments."""
    payload = json.dumps({"a": args, "k": kwargs}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def cached(bucket: str) -> Callable[[F], F]:
    """
    Decorator that caches the return value of a function in *bucket*.

    Usage::

        @cached("quotes")
        def get_quote(ticker: str) -> dict: ...
    """
    if bucket not in _BUCKETS:
        raise ValueError(f"Unknown cache bucket '{bucket}'. Valid: {list(_BUCKETS)}")

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = _make_key(fn.__qualname__, *args, **kwargs)
            cache = _BUCKETS[bucket]
            with _lock:
                if key in cache:
                    logger.debug("Cache HIT  [%s] %s", bucket, fn.__name__)
                    return cache[key]
            result = fn(*args, **kwargs)
            with _lock:
                cache[key] = result
            logger.debug("Cache MISS [%s] %s", bucket, fn.__name__)
            return result

        return wrapper  # type: ignore[return-value]

    return decorator


def invalidate(bucket: str, *args: Any, **kwargs: Any) -> None:
    """Remove a specific key from a bucket (best-effort)."""
    key = _make_key(*args, **kwargs)
    with _lock:
        _BUCKETS[bucket].pop(key, None)


def clear_bucket(bucket: str) -> None:
    """Wipe an entire cache bucket."""
    with _lock:
        _BUCKETS[bucket].clear()
    logger.info("Cleared cache bucket '%s'", bucket)


def stats() -> dict[str, dict[str, int]]:
    """Return hit/size statistics for all buckets (for diagnostics)."""
    with _lock:
        return {
            name: {"size": len(c), "maxsize": c.maxsize}
            for name, c in _BUCKETS.items()
        }
