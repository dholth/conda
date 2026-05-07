# Copyright (C) 2012 Anaconda, Inc
# SPDX-License-Identifier: BSD-3-Clause
"""HttpxFetch: Fetch adapter using httpx library.

Provides HTTP/2 support and other advanced features via httpx.
Currently a skeleton; full implementation in Phase 1b.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import io

    from ..response import FetchResponse


class HttpxFetch:
    """Fetch implementation using httpx.

    Supports:
    - HTTP/2 multiplexing
    - Async variants
    - Modern Python features

    TODO: Implement when httpx support is added (Phase 1b).
    """

    def __init__(self, http2: bool = True, **kwargs: Any):
        """Initialize HttpxFetch.

        Args:
            http2: Enable HTTP/2 support (default: True).
            **kwargs: Additional httpx.Client parameters.
        """
        # TODO: Implement
        raise NotImplementedError("HttpxFetch is not yet implemented (Phase 1b)")

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


__all__ = ["HttpxFetch"]
