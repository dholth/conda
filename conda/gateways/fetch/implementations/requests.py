# Copyright (C) 2012 Anaconda, Inc
# SPDX-License-Identifier: BSD-3-Clause
"""RequestsFetch: Fetch adapter wrapping requests.Session.

Provides a zero-overhead adapter implementing the Fetch protocol by wrapping
the existing conda requests.Session. This enables gradual migration away from
the Session-based API while maintaining full backward compatibility.
"""

from __future__ import annotations

import io
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any

from conda.gateways.connection import get_session

if TYPE_CHECKING:
    from requests import Response, Session


class RequestsResponse:
    """FetchResponse adapter wrapping requests.Response.

    Implements the FetchResponse protocol by delegating to a requests.Response.
    """

    def __init__(self, response: Response, request_url: str | None = None):
        """Initialize with requests.Response.

        Args:
            response: requests.Response object.
            request_url: Original request URL (for error reporting).
        """
        self._response = response
        self._request_url = request_url

    @property
    def status_code(self) -> int:
        """HTTP status code."""
        return self._response.status_code

    @property
    def headers(self) -> dict[str, str]:
        """Response headers as dict."""
        return dict(self._response.headers)

    @property
    def content(self) -> bytes:
        """Full response body as bytes.

        Raises:
            RuntimeError: If response is streaming.
        """
        # Check if response is streaming (raw stream not consumed)
        if self._response.raw.isclosed():
            return self._response.content
        else:
            raise RuntimeError(
                "Cannot read content property on streaming response. "
                "Use iter_bytes() instead."
            )

    @property
    def text(self) -> str:
        """Response body decoded as text.

        Raises:
            RuntimeError: If response is streaming.
        """
        if self._response.raw.isclosed():
            return self._response.text
        else:
            raise RuntimeError(
                "Cannot read text property on streaming response. "
                "Use iter_lines() instead."
            )

    def iter_bytes(self, chunk_size: int = 8192) -> Iterator[bytes]:
        """Iterate over response body in chunks.

        Args:
            chunk_size: Size of each chunk in bytes.

        Yields:
            Byte chunks.
        """
        yield from self._response.iter_content(chunk_size=chunk_size)

    def iter_lines(self, chunk_size: int = 8192) -> Iterator[str]:
        """Iterate over response body lines (decoded as text).

        Args:
            chunk_size: Internal buffer size for chunk reading.

        Yields:
            Lines of the response body.
        """
        # requests doesn't have iter_lines in modern versions; implement using iter_bytes
        buffer = ""
        for chunk in self.iter_bytes(chunk_size=chunk_size):
            buffer += chunk.decode("utf-8", errors="replace")
            lines = buffer.split("\n")
            # Yield all complete lines
            for line in lines[:-1]:
                yield line
            # Keep the incomplete last line in buffer
            buffer = lines[-1]
        # Yield any remaining content
        if buffer:
            yield buffer

    def raise_for_status(self) -> None:
        """Raise FetchHTTPError for 4xx/5xx status codes.

        Raises:
            FetchHTTPError: If status code indicates HTTP error.
        """
        from ..request import FetchHTTPError

        try:
            self._response.raise_for_status()
        except Exception as e:
            # Map requests.HTTPError to FetchHTTPError
            fetch_exc = FetchHTTPError(
                str(e), response=self, request_url=self._request_url
            )
            fetch_exc.__cause__ = e
            raise fetch_exc

    def json(self) -> Any:
        """Parse response body as JSON.

        Returns:
            Parsed JSON object.

        Raises:
            ValueError: If body is not valid JSON.
            RuntimeError: If response is streaming.
        """
        if self._response.raw.isclosed():
            return self._response.json()
        else:
            raise RuntimeError(
                "Cannot parse JSON on streaming response. "
                "Call .content property first to buffer response."
            )


class RequestsFetch:
    """Fetch implementation using requests.Session.

    Wraps conda's existing Session to implement the Fetch protocol with zero
    overhead and full backward compatibility.
    """

    def __init__(self, session: Session | None = None):
        """Initialize with optional session.

        Args:
            session: Optional requests.Session. If None, get the default from conda.
        """
        self.session = session or get_session()

    def head(self, url: str, **kwargs: Any) -> RequestsResponse:
        """Fetch HEAD request (metadata only).

        Args:
            url: URL to fetch.
            **kwargs: Additional parameters (headers, timeout, verify, auth, etc.).

        Returns:
            RequestsResponse wrapping requests.Response.

        Raises:
            FetchConnectionError: On connection error.
            FetchTimeout: On timeout.
            FetchSSLError: On SSL error.
        """
        try:
            resp = self.session.head(url, **kwargs)
            return RequestsResponse(resp, request_url=url)
        except Exception as e:
            self._map_exception(e)

    def get(self, url: str, stream: bool = False, **kwargs: Any) -> RequestsResponse:
        """Fetch GET request.

        Args:
            url: URL to fetch.
            stream: If True, body is not buffered. Use iter_bytes() to read.
            **kwargs: Additional parameters (headers, timeout, verify, auth, etc.).

        Returns:
            RequestsResponse wrapping requests.Response.

        Raises:
            FetchConnectionError: On connection error.
            FetchTimeout: On timeout.
            FetchSSLError: On SSL error.
            FetchHTTPError: On 4xx/5xx (if raise_for_status called).
        """
        try:
            resp = self.session.get(url, stream=stream, **kwargs)
            return RequestsResponse(resp, request_url=url)
        except Exception as e:
            self._map_exception(e)

    def get_file(
        self,
        url: str,
        fileobj: io.IOBase,
        progress_callback: Callable[[int, int], None] | None = None,
        **kwargs: Any,
    ) -> None:
        """Optimized file download to file object.

        Tries to use DirectDownloadAdapter if available (for special schemes like S3),
        otherwise falls back to streaming GET.

        Args:
            url: URL to download.
            fileobj: File-like object opened in binary write mode.
            progress_callback: Optional progress callback(bytes_downloaded, total_bytes).
            **kwargs: Additional parameters.

        Raises:
            FetchHTTPError: On HTTP error.
            IOError: On file write error.
        """
        from ..response import get_content_length

        try:
            # Try to use DirectDownloadAdapter for special handling
            adapter = self.session.get_adapter(url)
            if hasattr(adapter, "direct_download"):
                # Adapter supports direct download (e.g., S3)
                adapter.direct_download(url, fileobj, progress_callback)
                return

            # Fallback: streaming download
            resp = self.session.get(url, stream=True, **kwargs)
            resp.raise_for_status()

            # Get content length if available for progress reporting
            total_size = get_content_length(resp)

            # Stream response to file
            downloaded = 0
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:  # filter out keep-alive chunks
                    fileobj.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total_size:
                        progress_callback(downloaded, total_size)

        except Exception as e:
            self._map_exception(e)

    def _map_exception(self, exc: Exception) -> None:
        """Map requests exceptions to Fetch exceptions and raise.

        Args:
            exc: Exception from requests library.

        Raises:
            FetchException: Mapped exception.
        """
        from ..response import map_requests_exception

        fetch_exc = map_requests_exception(exc)
        raise fetch_exc


__all__ = ["RequestsFetch", "RequestsResponse"]
