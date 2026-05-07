# Copyright (C) 2012 Anaconda, Inc
# SPDX-License-Identifier: BSD-3-Clause
"""CurlFetch: Fetch adapter using pycurl library.

Provides true concurrent multiplexing via curl's multi interface.
Currently a skeleton; full implementation in Phase 1c.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import io

    from ..request import FetchRequest
    from ..types import FetchResponse


class CurlFetch:
    """Fetch implementation using pycurl.

    Supports:
    - True concurrent multiplexing (curl multi interface)
    - HTTP/2 with multiplexing
    - Advanced transfer options

    TODO: Implement when curl support is added (Phase 1c).
    """

    def __init__(self, **kwargs: Any):
        """Initialize CurlFetch.

        Args:
            **kwargs: Additional pycurl options.
        """
        # TODO: Implement
        raise NotImplementedError("CurlFetch is not yet implemented (Phase 1c)")

    def head(self, url: str, **kwargs: Any) -> FetchResponse:
        """Fetch HEAD request."""
        raise NotImplementedError()

    def get(self, url: str, stream: bool = False, **kwargs: Any) -> FetchResponse:
        """Fetch GET request."""
        raise NotImplementedError()

    def get_file(
        self,
        url: str,
        fileobj: io.IOBase,
        progress_callback: Callable[[int, int], None] | None = None,
        **kwargs: Any,
    ) -> None:
        """Download file."""
        raise NotImplementedError()


class CurlMultiplexer(CurlFetch):
    """FetchMultiplexer implementation using pycurl multi interface.

    Enables queue-based request dispatch and out-of-order response retrieval.

    TODO: Implement when curl support is added (Phase 1c).
    """

    def queue_fetch(self, request: FetchRequest) -> int:
        """Queue a fetch request."""
        raise NotImplementedError()

    def get_next_response(self, timeout: float | None = None) -> Any:
        """Get next response event."""
        raise NotImplementedError()

    def cancel_all(self) -> None:
        """Cancel all pending requests."""
        raise NotImplementedError()


__all__ = ["CurlFetch", "CurlMultiplexer"]
