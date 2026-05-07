# Copyright (C) 2012 Anaconda, Inc
# SPDX-License-Identifier: BSD-3-Clause
"""Request types and exception hierarchy for fetch operations.

Defines FetchRequest (unified request descriptor) and FetchException family
(unified exception hierarchy for mapping from different HTTP libraries).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .types import AuthHandler


@dataclass
class FetchRequest:
    """Unified HTTP request descriptor.

    Describes a request in a way that's agnostic to the underlying HTTP library.
    Can be used by any Fetch implementation.
    """

    url: str
    """Target URL."""

    method: str = "GET"
    """HTTP method (GET, HEAD, POST, etc.)."""

    headers: dict[str, str] | None = None
    """Request headers."""

    auth: AuthHandler | None = None
    """Auth handler to apply before sending."""

    timeout: tuple[float, float] | None = None
    """(connect_timeout, read_timeout) in seconds."""

    verify: bool | str = True
    """SSL verification: True (use defaults), False (disable), or path to CA bundle."""

    allow_redirects: bool = True
    """Follow HTTP redirects (3xx responses)."""

    stream: bool = False
    """If True, body is not buffered; use iter_bytes() to read."""

    params: dict[str, str | int] | None = None
    """Query parameters to append to URL."""

    data: bytes | str | None = None
    """Request body (for POST/PUT/PATCH)."""

    json: Any = None
    """Request body as JSON (alternative to data)."""

    proxies: dict[str, str] | None = None
    """Proxy URLs by scheme: {'http': 'http://proxy', 'https': 'https://proxy'}."""

    cert: str | tuple[str, str] | None = None
    """Client certificate: path to cert file, or (cert, key) tuple."""

    cookies: dict[str, str] | None = None
    """Cookies to send with request."""

    user_agent: str | None = None
    """User-Agent header (convenience)."""

    extra: dict[str, Any] = field(default_factory=dict)
    """Implementation-specific options not covered by standard fields."""


# =============================================================================
# Exception Hierarchy
# =============================================================================


class FetchException(Exception):
    """Base exception for all fetch errors.

    Subclasses map from library-specific exceptions (requests, httpx, curl)
    to a unified hierarchy, then to conda exceptions.
    """

    pass


class FetchConnectionError(FetchException):
    """Network connectivity error (DNS, connection refused, etc.)."""

    pass


class FetchTimeout(FetchException):
    """Request timeout (connect or read)."""

    pass


class FetchSSLError(FetchException):
    """SSL/TLS verification or certificate error."""

    pass


class FetchProxyError(FetchException):
    """Proxy-related error (connection, auth, etc.)."""

    pass


class FetchHTTPError(FetchException):
    """HTTP error response (4xx or 5xx status code).

    Attributes:
        response: The FetchResponse object with error status/body.
        request_url: URL that was requested.
    """

    def __init__(self, message: str, response=None, request_url: str | None = None):
        super().__init__(message)
        self.response = response
        self.request_url = request_url or (
            response.url if hasattr(response, "url") else None
        )


class FetchRedirectError(FetchException):
    """Too many redirects or redirect loop detected."""

    pass


# =============================================================================
# Error context information
# =============================================================================


@dataclass
class FetchErrorContext:
    """Additional context about a fetch error.

    Useful for logging and debugging. Contains both request and response info.
    """

    request: FetchRequest | None = None
    response: Any = None  # FetchResponse or None
    original_exception: Exception | None = None
    library_name: str | None = None  # 'requests', 'httpx', 'curl', etc.
    retry_count: int = 0
    """Number of retries attempted."""

    elapsed_time: float | None = None
    """Seconds elapsed before error."""
