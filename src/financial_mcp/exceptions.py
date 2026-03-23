"""
Domain-specific exceptions for the financial MCP server.

Every adapter should translate third-party library errors into one of these
so that the tool layer can produce consistent, user-friendly error messages.
"""

from __future__ import annotations


class FinancialMCPError(Exception):
    """Base class for all errors raised by this server."""


class SourceUnavailableError(FinancialMCPError):
    """
    Raised when a data source is temporarily unavailable (network error,
    service down, etc.).  The tool layer should try the next fallback source.
    """

    def __init__(self, source: str, reason: str = "") -> None:
        self.source = source
        super().__init__(f"Source '{source}' unavailable: {reason}" if reason else f"Source '{source}' unavailable")


class RateLimitError(FinancialMCPError):
    """Raised when a source's rate limit / daily quota has been exceeded."""

    def __init__(self, source: str) -> None:
        self.source = source
        super().__init__(f"Rate limit exceeded for source '{source}'")


class MissingAPIKeyError(FinancialMCPError):
    """Raised when a required API key is absent or is still the placeholder value."""

    def __init__(self, source: str, env_var: str) -> None:
        self.source = source
        self.env_var = env_var
        super().__init__(
            f"API key for '{source}' is missing. "
            f"Set {env_var} in your .env file. "
            f"See .env.example for instructions."
        )


class TickerNotFoundError(FinancialMCPError):
    """Raised when a ticker symbol cannot be resolved by the source."""

    def __init__(self, ticker: str, source: str = "") -> None:
        self.ticker = ticker
        self.source = source
        msg = f"Ticker '{ticker}' not found"
        if source:
            msg += f" in {source}"
        super().__init__(msg)


class DataParseError(FinancialMCPError):
    """Raised when the response from a source cannot be parsed as expected."""

    def __init__(self, source: str, detail: str = "") -> None:
        self.source = source
        super().__init__(f"Failed to parse response from '{source}': {detail}")
