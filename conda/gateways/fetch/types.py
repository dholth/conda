# Copyright (C) 2012 Anaconda, Inc
# SPDX-License-Identifier: BSD-3-Clause
"""Core Protocol interfaces for pluggable HTTP fetch implementations.

This module defines the abstract interfaces that any HTTP library (requests, httpx, curl)
must implement to be used as a fetch backend. Uses Python's typing.Protocol for flexible,
duck-typed interfaces without base class coupling.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from io import IOBase
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class FetchResponse(Protocol):
    """Response from a Fetch operation.

    This protocol defines the interface for HTTP responses. Implementations should
    provide both streaming and non-streaming access, but raise errors if accessed
    incorrectly (e.g., accessing .content on a streaming response).
    """

    @property
    def status_code(self) -> int:
        """HTTP status code (e.g., 200, 404, 500)."""
        ...

    @property
    def headers(self) -> dict[str, str]:
        """Response headers as a dictionary."""
        ...

    @property
    def content(self) -> bytes:
        """Full response body as bytes.

        Raises:
            RuntimeError: If response is streaming (not fully buffered).
        """
        ...

    @property
    def text(self) -> str:
        """Response body as decoded text.

        Raises:
            RuntimeError: If response is streaming (not fully buffered).
        """
        ...

    def iter_bytes(self, chunk_size: int = 8192) -> Iterator[bytes]:
        """Iterate over response body in chunks.

        Args:
            chunk_size: Number of bytes per chunk (default 8192).

        Yields:
            Byte chunks of the response body.
        """
        ...

    def iter_lines(self, chunk_size: int = 8192) -> Iterator[str]:
        """Iterate over response body lines (decoded as text).

        Args:
            chunk_size: Internal buffer size for chunk reading.

        Yields:
            Lines of the response body (line endings stripped).
        """
        ...

    def raise_for_status(self) -> None:
        """Raise an exception for 4xx/5xx status codes.

        Raises:
            FetchHTTPError: If status code indicates HTTP error.
        """
        ...

    def json(self) -> Any:
        """Parse response body as JSON.

        Returns:
            Parsed JSON object/array/etc.

        Raises:
            ValueError: If body is not valid JSON.
            RuntimeError: If response is streaming.
        """
        ...


@runtime_checkable
class Fetch(Protocol):
    """Protocol for HTTP fetch implementations.

    Similar to unearth's approach, this allows any HTTP library (requests, httpx, curl)
    to be used interchangeably if it implements this interface.

    Implementations must provide:
    - get(): Fetch a URL with GET request
    - head(): Fetch a URL with HEAD request
    - get_file(): Optimized file download
    """

    def head(self, url: str, **kwargs: Any) -> FetchResponse:
        """Fetch HEAD request (metadata only).

        Args:
            url: URL to fetch.
            **kwargs: Optional parameters (headers, timeout, allow_redirects, etc.).

        Returns:
            FetchResponse with headers but no body.

        Raises:
            FetchException: On network or HTTP errors.
        """
        ...

    def get(self, url: str, stream: bool = False, **kwargs: Any) -> FetchResponse:
        """Fetch GET request.

        Args:
            url: URL to fetch.
            stream: If True, body is not buffered; use iter_bytes() to read.
            **kwargs: Optional parameters (headers, timeout, auth, allow_redirects, etc.).

        Returns:
            FetchResponse with status, headers, and body.

        Raises:
            FetchException: On network or HTTP errors.
        """
        ...

    def get_file(
        self,
        url: str,
        fileobj: IOBase,
        progress_callback: Callable[[int, int], None] | None = None,
        **kwargs: Any,
    ) -> None:
        """Optimized file download to a file-like object.

        This method enables library-specific optimizations (e.g., direct download
        adapter, progress reporting, resumable downloads). Falls back to streaming
        get() if not implemented.

        Args:
            url: URL to download.
            fileobj: File-like object opened in binary write mode.
            progress_callback: Optional callback(bytes_downloaded, total_bytes).
                               Called as chunks are written.
            **kwargs: Optional parameters passed to underlying library.

        Raises:
            FetchException: On network or HTTP errors.
            IOError: On file write errors.
        """
        ...


@runtime_checkable
class FetchMultiplexer(Fetch, Protocol):
    """Optional protocol for concurrent/multiplexed fetch implementations.

    Enables queue-based request dispatch without blocking on individual requests.
    Useful for downloading many files concurrently. Inspired by conda-libmamba-solver's
    shard implementation and curl's multi interface.

    Implementations should support:
    - Queuing multiple requests non-blocking
    - Retrieving responses out-of-order
    - Progress events during download
    - Request cancellation
    """

    def queue_fetch(self, request: FetchRequest) -> int:
        """Queue a fetch request (non-blocking).

        Args:
            request: FetchRequest describing the download.

        Returns:
            Request ID for tracking/cancellation.

        Raises:
            FetchException: If queue is full or invalid request.
        """
        ...

    def get_next_response(self, timeout: float | None = None) -> FetchResponseEvent:
        """Get next response event (response, error, or progress).

        Blocks until a response is available or timeout expires.

        Args:
            timeout: Seconds to wait for next event (None = wait forever).

        Returns:
            FetchResponseEvent (union of response/error/progress variants).

        Raises:
            TimeoutError: If timeout expires with no events.
        """
        ...

    def cancel_all(self) -> None:
        """Cancel all pending requests."""
        ...


@runtime_checkable
class AuthHandler(Protocol):
    """Protocol for HTTP authentication.

    Implementations handle applying credentials to requests and responding
    to authentication challenges (401/407 responses).
    """

    def apply(self, request: FetchRequest) -> FetchRequest:
        """Apply authentication to a request.

        Args:
            request: FetchRequest to augment with auth.

        Returns:
            Modified FetchRequest with authentication headers/params.
        """
        ...

    def handle_challenge(self, response: FetchResponse) -> bool:
        """Handle 401/407 response from server.

        Called when server challenges authentication. Implementation should
        determine if retry is possible (e.g., refresh token) and return True
        to retry, or False to fail.

        Args:
            response: FetchResponse with 401/407 status.

        Returns:
            True if request should be retried, False to fail.
        """
        ...


# Type aliases for convenience
FetchCallable = Callable[..., FetchResponse]
ProgressCallback = Callable[[int, int], None]


# =============================================================================
# TODO: Define FetchRequest and FetchResponseEvent types
# These are currently defined in request.py, but might be better here
# for logical grouping. See questions in OPERATOR.md.
# =============================================================================
