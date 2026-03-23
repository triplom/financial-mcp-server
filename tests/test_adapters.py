"""
Adapter unit tests — all external network calls are mocked.
Run with: pytest tests/
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


# ── yfinance adapter ───────────────────────────────────────────────────────────

class TestYfinanceAdapter:

    def test_get_quote_returns_expected_keys(self):
        mock_info = {
            "regularMarketPrice": 175.0,
            "regularMarketPreviousClose": 170.0,
            "regularMarketOpen": 171.0,
            "regularMarketDayHigh": 176.0,
            "regularMarketDayLow": 169.0,
            "regularMarketVolume": 50_000_000,
            "marketCap": 2_700_000_000_000,
            "currency": "USD",
            "exchange": "NMS",
            "longName": "Apple Inc.",
            "quoteType": "EQUITY",
        }
        with patch("yfinance.Ticker") as MockTicker:
            instance = MockTicker.return_value
            instance.info = mock_info
            # Clear cache so test is isolated
            from financial_mcp.cache import clear_bucket
            clear_bucket("quotes")
            from financial_mcp.adapters.yfinance_adapter import get_quote
            result = get_quote("AAPL")

        assert result["symbol"] == "AAPL"
        assert result["price"] == 175.0
        assert result["change"] == pytest.approx(5.0)
        assert result["change_pct"] == pytest.approx(5.0 / 170.0 * 100, rel=1e-3)
        assert result["source"] == "yfinance"

    def test_get_quote_raises_on_empty_info(self):
        with patch("yfinance.Ticker") as MockTicker:
            instance = MockTicker.return_value
            instance.info = {}
            from financial_mcp.cache import clear_bucket
            clear_bucket("quotes")
            from financial_mcp.adapters.yfinance_adapter import get_quote
            from financial_mcp.exceptions import TickerNotFoundError
            with pytest.raises(TickerNotFoundError):
                get_quote("FAKEXYZ")

    def test_get_price_history_returns_list(self):
        import pandas as pd
        mock_df = pd.DataFrame(
            {"Open": [100.0], "High": [105.0], "Low": [99.0], "Close": [103.0], "Volume": [1_000_000]},
            index=pd.to_datetime(["2024-01-02"]),
        )
        with patch("yfinance.Ticker") as MockTicker:
            instance = MockTicker.return_value
            instance.history.return_value = mock_df
            from financial_mcp.cache import clear_bucket
            clear_bucket("eod_prices")
            from financial_mcp.adapters.yfinance_adapter import get_price_history
            result = get_price_history("AAPL", period="1d", interval="1d")

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["close"] == 103.0

    def test_get_options_chain_structure(self):
        import pandas as pd
        mock_chain = MagicMock()
        mock_chain.calls = pd.DataFrame([{"strike": 175.0, "lastPrice": 2.5}])
        mock_chain.puts  = pd.DataFrame([{"strike": 175.0, "lastPrice": 1.8}])
        with patch("yfinance.Ticker") as MockTicker:
            instance = MockTicker.return_value
            instance.options = ("2024-06-21",)
            instance.option_chain.return_value = mock_chain
            from financial_mcp.cache import clear_bucket
            clear_bucket("quotes")
            from financial_mcp.adapters.yfinance_adapter import get_options_chain
            result = get_options_chain("AAPL")

        assert "calls" in result
        assert "puts" in result
        assert result["expiration"] == "2024-06-21"

    def test_get_forex_rate(self):
        mock_info = {"regularMarketPrice": 1.085, "bid": 1.085}
        with patch("yfinance.Ticker") as MockTicker:
            instance = MockTicker.return_value
            instance.info = mock_info
            from financial_mcp.cache import clear_bucket
            clear_bucket("quotes")
            from financial_mcp.adapters.yfinance_adapter import get_forex_rate
            result = get_forex_rate("EUR", "USD")

        assert result["pair"] == "EUR/USD"
        assert result["rate"] == pytest.approx(1.085)


# ── FRED adapter ───────────────────────────────────────────────────────────────

class TestFredAdapter:

    def test_series_id_alias_resolution(self):
        from financial_mcp.adapters.fred_adapter import _series_id
        assert _series_id("cpi") == "CPIAUCSL"
        assert _series_id("unemployment") == "UNRATE"
        assert _series_id("10y_treasury") == "DGS10"
        # Raw FRED IDs should pass through uppercased
        assert _series_id("GDPC1") == "GDPC1"
        assert _series_id("gdpc1") == "GDPC1"

    def test_get_series_raises_without_key(self, monkeypatch):
        monkeypatch.setenv("FRED_API_KEY", "")
        from financial_mcp.exceptions import MissingAPIKeyError
        # Reload config to pick up monkeypatched env
        import importlib
        import financial_mcp.config as cfg_mod
        import financial_mcp.adapters.fred_adapter as fred_mod
        importlib.reload(cfg_mod)
        importlib.reload(fred_mod)
        from financial_mcp.cache import clear_bucket
        clear_bucket("fred")
        with pytest.raises(MissingAPIKeyError):
            fred_mod.get_series("cpi")

    def test_list_well_known_series_returns_dict(self):
        from financial_mcp.adapters.fred_adapter import list_well_known_series
        result = list_well_known_series()
        assert isinstance(result, dict)
        assert "cpi" in result
        assert "gdp" in result
        assert len(result) >= 20


# ── CoinGecko adapter ──────────────────────────────────────────────────────────

class TestCoinGeckoAdapter:

    def test_resolve_coin_id_by_symbol(self):
        mock_coins = [
            {"id": "bitcoin",  "symbol": "btc",  "name": "Bitcoin"},
            {"id": "ethereum", "symbol": "eth",  "name": "Ethereum"},
            {"id": "solana",   "symbol": "sol",  "name": "Solana"},
        ]
        with patch("pycoingecko.CoinGeckoAPI.get_coins_list", return_value=mock_coins):
            from financial_mcp.cache import clear_bucket
            clear_bucket("crypto")
            from financial_mcp.adapters.coingecko_adapter import resolve_coin_id
            assert resolve_coin_id("BTC") == "bitcoin"
            assert resolve_coin_id("bitcoin") == "bitcoin"
            assert resolve_coin_id("eth") == "ethereum"

    def test_resolve_coin_id_raises_for_unknown(self):
        mock_coins = [{"id": "bitcoin", "symbol": "btc", "name": "Bitcoin"}]
        with patch("pycoingecko.CoinGeckoAPI.get_coins_list", return_value=mock_coins):
            from financial_mcp.cache import clear_bucket
            clear_bucket("crypto")
            from financial_mcp.adapters.coingecko_adapter import resolve_coin_id
            from financial_mcp.exceptions import TickerNotFoundError
            with pytest.raises(TickerNotFoundError):
                resolve_coin_id("FAKECOIN999")


# ── Cache ──────────────────────────────────────────────────────────────────────

class TestCache:

    def test_cache_hit(self):
        from financial_mcp.cache import cached, clear_bucket

        call_count = 0

        @cached("quotes")
        def expensive(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2

        clear_bucket("quotes")
        r1 = expensive(42)
        r2 = expensive(42)
        assert r1 == r2 == 84
        assert call_count == 1  # second call was a cache hit

    def test_cache_miss_different_args(self):
        from financial_mcp.cache import cached, clear_bucket

        call_count = 0

        @cached("quotes")
        def double(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2

        clear_bucket("quotes")
        double(1)
        double(2)
        assert call_count == 2

    def test_cache_stats_returns_all_buckets(self):
        from financial_mcp.cache import stats
        result = stats()
        assert "quotes" in result
        assert "fred" in result
        assert "sec_filings" in result
        assert "crypto" in result


# ── Rate limiter ───────────────────────────────────────────────────────────────

class TestRateLimiter:

    def test_acquire_does_not_raise_for_known_source(self):
        from financial_mcp.rate_limiter import acquire
        # Should not raise — may sleep briefly on first call
        acquire("fred")

    def test_acquire_logs_warning_for_unknown_source(self, caplog):
        import logging
        from financial_mcp.rate_limiter import acquire
        with caplog.at_level(logging.WARNING, logger="financial_mcp.rate_limiter"):
            acquire("nonexistent_source_xyz")
        assert "No rate limiter" in caplog.text

    def test_backoff_increases_interval(self):
        from financial_mcp.rate_limiter import _LIMITERS, backoff
        original = _LIMITERS["fred"].min_interval
        backoff("fred", factor=2.0)
        assert _LIMITERS["fred"].min_interval == pytest.approx(original * 2.0)
        # Restore
        _LIMITERS["fred"].min_interval = original


# ── Exceptions ─────────────────────────────────────────────────────────────────

class TestExceptions:

    def test_missing_api_key_error_message(self):
        from financial_mcp.exceptions import MissingAPIKeyError
        exc = MissingAPIKeyError("FRED", "FRED_API_KEY")
        assert "FRED_API_KEY" in str(exc)
        assert "FRED" in str(exc)

    def test_ticker_not_found_error(self):
        from financial_mcp.exceptions import TickerNotFoundError
        exc = TickerNotFoundError("FAKE", "yfinance")
        assert "FAKE" in str(exc)
        assert "yfinance" in str(exc)

    def test_rate_limit_error(self):
        from financial_mcp.exceptions import RateLimitError
        exc = RateLimitError("alpha_vantage")
        assert "alpha_vantage" in str(exc)
