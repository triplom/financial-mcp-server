# Financial MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server that
aggregates **free public financial data** from multiple sources into a single
unified interface for AI assistants (Claude, Cursor, VS Code Copilot, etc.).

## What it provides

| Domain | Tools | Sources |
|---|---|---|
| **Equities** | Quote, price history, options chain, fundamentals, news, company profile | yfinance, Tiingo |
| **SEC / Regulatory** | Financial statements (XBRL), filing history, insider transactions | SEC EDGAR |
| **Macroeconomics** | 800k+ FRED series, yield curve, inflation snapshot, series search | FRED |
| **Crypto** | Price, multi-coin prices, OHLC history, global market overview, trending | CoinGecko |
| **Forex** | Spot rates for all major/minor pairs | Polygon.io → yfinance |
| **Commodities** | WTI, Brent, natural gas, gold, silver, copper, grains, soft commodities | Alpha Vantage → yfinance futures |
| **Technical Analysis** | RSI, MACD, Bollinger Bands, SMA 50/200 | Alpha Vantage |
| **Diagnostics** | Server status, configured sources, cache statistics | Built-in |

**21 tools total.**

## Quick start

### 1. Install

```bash
# Requires Python 3.10+
git clone <repo>
cd financial-mcp-server
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

### 2. Configure API keys

```bash
cp .env.example .env
# Edit .env and add your keys
```

**Required** (server will not serve macro data without this):
- `FRED_API_KEY` — [Get free key](https://fred.stlouisfed.org/docs/api/api_key.html)

**Optional** (server degrades gracefully if missing):
- `TIINGO_API_KEY` — [Get free key](https://www.tiingo.com/account/api/token) (better news + validated historical data)
- `POLYGON_API_KEY` — [Get free key](https://polygon.io/) (better forex + real-time crypto)
- `ALPHA_VANTAGE_API_KEY` — [Get free key](https://www.alphavantage.co/support/#api-key) (technical indicators, commodities — WARNING: 25 req/day free)
- `COINGECKO_API_KEY` — [Get demo key](https://www.coingecko.com/en/api) (higher rate limits)

yfinance, SEC EDGAR, and CoinGecko (public tier) require **no API keys**.

### 3. Run

```bash
financial-mcp-server
# or:
python -m financial_mcp.server
```

### 4. Connect to Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "financial": {
      "command": "/path/to/.venv/bin/financial-mcp-server"
    }
  }
}
```

Or with `uvx` (no install needed):
```json
{
  "mcpServers": {
    "financial": {
      "command": "uvx",
      "args": ["--from", "financial-mcp-server", "financial-mcp-server"]
    }
  }
}
```

## Available tools

### Equities

| Tool | Description |
|---|---|
| `get_stock_quote` | Real-time (15-min delayed) quote: price, change, market cap |
| `get_price_history` | OHLCV bars — daily/weekly/monthly or intraday (1m–1h) |
| `get_options_chain` | Full options chain: calls & puts with greeks |
| `get_fundamentals` | P/E, P/B, margins, ROE, dividends, analyst targets |
| `get_financial_statements` | Annual income statement, balance sheet, cash flow from SEC |
| `get_sec_filings` | 10-K, 10-Q, 8-K, proxy, insider filings with direct links |
| `get_insider_transactions` | Form 4 insider buy/sell filings |
| `get_stock_news` | Recent news with topic tags (via Tiingo or yfinance) |
| `get_ticker_details` | Company profile: sector, description, employees, website |

### Macroeconomics (FRED)

| Tool | Description |
|---|---|
| `get_macro_series` | Any of 800k+ FRED series by alias or raw ID |
| `get_yield_curve` | Full US Treasury yield curve with inversion flag |
| `get_inflation_snapshot` | CPI, core CPI, PCE, core PCE with YoY changes |
| `search_fred_series` | Search for FRED series by keyword |
| `list_well_known_fred_series` | List all built-in friendly aliases |

### Crypto

| Tool | Description |
|---|---|
| `get_crypto_price` | Full market data for any of 10,000+ coins |
| `get_crypto_prices` | Prices for multiple coins in one call |
| `get_crypto_history` | Historical OHLC data (up to "max") |
| `get_crypto_market_overview` | Global market cap, BTC dominance, 24h volume |
| `get_trending_crypto` | Top 7 trending coins in last 24h |
| `get_crypto_news` | Crypto news with ticker tags (requires Tiingo key) |

### Forex & Commodities

| Tool | Description |
|---|---|
| `get_forex_rate` | Spot FX rate for any currency pair |
| `get_commodity_price` | Historical prices: oil, gas, metals, grains, softs |
| `get_technical_indicators` | RSI, MACD, Bollinger Bands, SMA (requires Alpha Vantage) |

### Diagnostics

| Tool | Description |
|---|---|
| `get_server_status` | Which sources are configured, cache stats |

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   MCP Client (Claude)                │
└──────────────────────────┬──────────────────────────┘
                           │ stdio (JSON-RPC 2.0)
┌──────────────────────────▼──────────────────────────┐
│              financial-mcp-server                    │
│  ┌──────────────────────────────────────────────┐   │
│  │              Tool Layer (21 tools)            │   │
│  │  equities.py  macro.py  crypto.py  forex.py  │   │
│  └────────────────────┬─────────────────────────┘   │
│  ┌─────────┐  ┌───────▼──────────────────────────┐  │
│  │  Cache  │  │         Adapter Layer             │  │
│  │  (TTL)  │  │  yfinance  fred  sec  coingecko   │  │
│  └────┬────┘  │  tiingo  polygon  alpha_vantage   │  │
│       │       └───────────────────────────────────┘  │
│  ┌────▼─────────────────────────────────────────┐    │
│  │         Rate Limiter (per-source)            │    │
│  └──────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────┘
```

## Rate limits & caching

| Source | Free Limit | Cache TTL |
|---|---|---|
| yfinance | ~1 req/sec | 60s (quotes), 24h (EOD) |
| FRED | 120 req/60s | 24h |
| SEC EDGAR | 10 req/sec | 7 days |
| CoinGecko | 30 req/min (demo) | 120s |
| Tiingo | 50 req/hr | 15m (news), 24h (prices) |
| Polygon | 5 req/min | 60s (quotes) |
| Alpha Vantage | **25 req/day** | 24h (critical — cache aggressively) |

## Development

```bash
pip install -e ".[dev]"
pytest tests/          # run unit tests (all mocked, no network)
ruff check src/        # lint
mypy src/              # type-check
```

## License

MIT
