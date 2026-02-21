"""maestro-fetch error hierarchy.

All domain errors inherit from FetchError so callers can catch
a single base class for broad handling, or specific subclasses
for targeted recovery.
"""


class FetchError(Exception):
    """Base error for all maestro-fetch failures."""


class UnsupportedURLError(FetchError):
    """No adapter supports this URL."""


class DownloadError(FetchError):
    """Network or HTTP error during download."""


class ParseError(FetchError):
    """Document parsing failed."""


class ProviderError(FetchError):
    """LLM provider call failed."""
