# Copyright (C) 2012 Anaconda, Inc
# SPDX-License-Identifier: BSD-3-Clause
"""Response handling and error mapping for fetch operations.

Maps library-specific exceptions and status codes to unified Fetch exceptions,
then to conda exceptions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .request import FetchException
    from .types import FetchResponse


# =============================================================================
# Status Code Handling
# =============================================================================


def is_http_error(status_code: int) -> bool:
    """Check if status code indicates an HTTP error (4xx or 5xx).

    Args:
        status_code: HTTP status code.

    Returns:
        True if status indicates error.
    """
    return 400 <= status_code < 600


def get_http_error_name(status_code: int) -> str:
    """Get human-readable name for HTTP status code.

    Args:
        status_code: HTTP status code (e.g., 404).

    Returns:
        Status name (e.g., "Not Found").
    """
    # Simple mapping; could be expanded
    status_names = {
        400: "Bad Request",
        401: "Unauthorized",
        402: "Payment Required",
        403: "Forbidden",
        404: "Not Found",
        405: "Method Not Allowed",
        406: "Not Acceptable",
        407: "Proxy Authentication Required",
        408: "Request Timeout",
        409: "Conflict",
        410: "Gone",
        429: "Too Many Requests",
        500: "Internal Server Error",
        501: "Not Implemented",
        502: "Bad Gateway",
        503: "Service Unavailable",
        504: "Gateway Timeout",
    }
    return status_names.get(status_code, f"HTTP {status_code}")


# =============================================================================
# Exception Mapping: Library → Fetch → Conda
# =============================================================================


def map_requests_exception(exc: Exception) -> FetchException:
    """Map requests library exceptions to Fetch exceptions.

    Args:
        exc: Exception from requests library.

    Returns:
        Corresponding FetchException.

    Raises:
        FetchException: The mapped exception.
    """
    # Lazy imports to avoid circular dependencies
    import requests

    from .request import (
        FetchConnectionError,
        FetchException,
        FetchHTTPError,
        FetchProxyError,
        FetchSSLError,
        FetchTimeout,
    )

    # Map specific requests exceptions
    if isinstance(exc, requests.Timeout):
        fetch_exc = FetchTimeout(str(exc))
    elif isinstance(exc, requests.ConnectionError):
        fetch_exc = FetchConnectionError(str(exc))
    elif isinstance(exc, requests.HTTPError):
        fetch_exc = FetchHTTPError(str(exc))
    elif isinstance(exc, requests.URLRequired):
        fetch_exc = FetchException(f"Invalid URL: {exc}")
    elif isinstance(exc, requests.RequestException):
        # Generic requests error
        if "ssl" in str(exc).lower():
            fetch_exc = FetchSSLError(str(exc))
        elif "proxy" in str(exc).lower():
            fetch_exc = FetchProxyError(str(exc))
        else:
            fetch_exc = FetchConnectionError(str(exc))
    else:
        # Unknown exception type
        fetch_exc = FetchException(f"Unknown requests error: {exc}")

    # Set exception cause for proper chaining
    fetch_exc.__cause__ = exc
    return fetch_exc


def map_httpx_exception(exc: Exception) -> FetchException:
    """Map httpx library exceptions to Fetch exceptions.

    Args:
        exc: Exception from httpx library.

    Returns:
        Corresponding FetchException.
    """
    # TODO: Implement when httpx support is added
    from .request import FetchException

    fetch_exc = FetchException(f"httpx error: {exc}")
    fetch_exc.__cause__ = exc
    return fetch_exc


def map_pycurl_exception(exc: Exception) -> FetchException:
    """Map pycurl library exceptions to Fetch exceptions.

    Args:
        exc: Exception from pycurl library.

    Returns:
        Corresponding FetchException.
    """
    # TODO: Implement when curl support is added
    from .request import FetchException

    fetch_exc = FetchException(f"pycurl error: {exc}")
    fetch_exc.__cause__ = exc
    return fetch_exc


# =============================================================================
# Response Validation
# =============================================================================


def validate_response(response: FetchResponse, raise_on_error: bool = True) -> bool:
    """Validate response and optionally raise on HTTP errors.

    Args:
        response: FetchResponse to validate.
        raise_on_error: If True, raise FetchHTTPError for 4xx/5xx status.

    Returns:
        True if response is valid.

    Raises:
        FetchHTTPError: If raise_on_error is True and status is 4xx/5xx.
    """
    if is_http_error(response.status_code):
        if raise_on_error:
            response.raise_for_status()
        return False
    return True


# =============================================================================
# Response Introspection
# =============================================================================


def get_content_length(response: FetchResponse) -> int | None:
    """Extract content length from response headers.

    Args:
        response: FetchResponse to inspect.

    Returns:
        Content length in bytes, or None if not specified.
    """
    content_length = response.headers.get("content-length")
    if content_length:
        try:
            return int(content_length)
        except ValueError:
            return None
    return None


def is_chunked_encoding(response: FetchResponse) -> bool:
    """Check if response uses chunked transfer encoding.

    Args:
        response: FetchResponse to inspect.

    Returns:
        True if chunked encoding is used.
    """
    transfer_encoding = response.headers.get("transfer-encoding", "").lower()
    return "chunked" in transfer_encoding


def is_gzip_compressed(response: FetchResponse) -> bool:
    """Check if response body is gzip-compressed.

    Args:
        response: FetchResponse to inspect.

    Returns:
        True if gzip compression is used.
    """
    content_encoding = response.headers.get("content-encoding", "").lower()
    return "gzip" in content_encoding


def get_charset(response: FetchResponse) -> str:
    """Extract character encoding from response headers.

    Args:
        response: FetchResponse to inspect.

    Returns:
        Character encoding name (default: 'utf-8').
    """
    content_type = response.headers.get("content-type", "")
    # Simple parsing: look for "charset=..."
    if "charset=" in content_type:
        charset = content_type.split("charset=")[-1].split(";")[0].strip()
        return charset or "utf-8"
    return "utf-8"
