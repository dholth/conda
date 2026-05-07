# Copyright (C) 2012 Anaconda, Inc
# SPDX-License-Identifier: BSD-3-Clause
"""Pluggable HTTP fetch interface for conda.

This module provides a protocol-based abstraction layer over different HTTP libraries
(requests, httpx, curl). Enables conda to support HTTP/2, multiplexing, and other
advanced features while maintaining backward compatibility.

Key concepts:
- Fetch: Protocol for HTTP fetch implementations
- FetchResponse: Protocol for HTTP responses
- FetchRequest: Unified request descriptor
- Registry: Runtime selection and registration of fetch implementations
- AuthHandler: Protocol for authentication handling
"""

from __future__ import annotations

from .auth import (
    BasicAuthHandler,
    BearerTokenAuthHandler,
    ChannelAuthResolver,
    get_default_auth_resolver,
)
from .registry import (
    clear_fetch_cache,
    get_fetch,
    get_fetch_cached,
    list_fetches,
    register_fetch,
    set_fetch,
)
from .request import (
    FetchConnectionError,
    FetchException,
    FetchHTTPError,
    FetchProxyError,
    FetchRedirectError,
    FetchRequest,
    FetchSSLError,
    FetchTimeout,
)
from .types import AuthHandler, Fetch, FetchMultiplexer, FetchResponse

__all__ = [
    # Protocols
    "Fetch",
    "FetchResponse",
    "FetchMultiplexer",
    "AuthHandler",
    # Requests & exceptions
    "FetchRequest",
    "FetchException",
    "FetchConnectionError",
    "FetchHTTPError",
    "FetchProxyError",
    "FetchSSLError",
    "FetchTimeout",
    "FetchRedirectError",
    # Auth handlers
    "BasicAuthHandler",
    "BearerTokenAuthHandler",
    "ChannelAuthResolver",
    "get_default_auth_resolver",
    # Registry
    "get_fetch",
    "get_fetch_cached",
    "set_fetch",
    "register_fetch",
    "list_fetches",
    "clear_fetch_cache",
]
