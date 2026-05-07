# Copyright (C) 2012 Anaconda, Inc
# SPDX-License-Identifier: BSD-3-Clause
"""Registry for discovering and managing Fetch implementations.

Allows runtime registration and lookup of Fetch implementations by name.
Supports environment variable override for testing/selection.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .types import Fetch


# Global registry of available fetch implementations
_FETCHES: dict[str, type[Fetch]] = {}

# Currently selected fetch implementation
_current_fetch: Fetch | None = None


def register_fetch(name: str, fetch_class: type[Fetch]) -> None:
    """Register a Fetch implementation.

    Args:
        name: Short name for this fetch (e.g., 'requests', 'httpx', 'curl').
        fetch_class: Class implementing Fetch protocol.

    Raises:
        TypeError: If fetch_class doesn't implement Fetch protocol.
    """
    # TODO: Validate that fetch_class actually implements Fetch protocol
    _FETCHES[name] = fetch_class


def get_fetch(name: str | None = None) -> Fetch:
    """Get a Fetch instance by name.

    Selection priority:
    1. Explicit name parameter
    2. CONDA_FETCH environment variable
    3. Default ('requests')

    Args:
        name: Optional fetch name. If None, check env var or use default.

    Returns:
        Fetch instance ready to use.

    Raises:
        ValueError: If requested fetch is not registered.
        ImportError: If fetch requires optional dependency that's not installed.
    """
    if name is None:
        name = os.environ.get("CONDA_FETCH", "requests")

    if name not in _FETCHES:
        raise ValueError(f"Unknown fetch: {name!r}. Available: {list(_FETCHES.keys())}")

    fetch_class = _FETCHES[name]
    return fetch_class()


def get_fetch_cached(name: str | None = None) -> Fetch:
    """Get or create a cached Fetch instance.

    Useful for request pooling (HTTP connection pools, etc.).

    Args:
        name: Optional fetch name (same as get_fetch).

    Returns:
        Cached Fetch instance.
    """
    global _current_fetch

    if name is None:
        name = os.environ.get("CONDA_FETCH", "requests")

    # If we have a cached fetch of the right type, return it
    # TODO: Track which implementation is currently cached
    if _current_fetch is not None:
        return _current_fetch

    # Create new instance and cache it
    _current_fetch = get_fetch(name)
    return _current_fetch


def set_fetch(name: str, fetch_class: type[Fetch]) -> None:
    """Register a Fetch implementation (alias for register_fetch).

    Args:
        name: Short name for this fetch.
        fetch_class: Class implementing Fetch protocol.
    """
    register_fetch(name, fetch_class)


def list_fetches() -> dict[str, type[Fetch]]:
    """List all registered Fetch implementations.

    Returns:
        Dictionary mapping names to fetch classes.
    """
    return _FETCHES.copy()


def clear_fetch_cache() -> None:
    """Clear the cached Fetch instance.

    Useful for testing or when settings change.
    """
    global _current_fetch
    _current_fetch = None


# =============================================================================
# Built-in Registration
# =============================================================================


def register_builtin_fetches() -> None:
    """Register built-in fetch implementations.

    Called automatically when this module is imported.
    Tries to import each built-in implementation; gracefully skips if
    optional dependencies are missing.
    """
    # RequestsFetch (always available - requests is a core dependency)
    try:
        from .implementations.requests import RequestsFetch

        register_fetch("requests", RequestsFetch)
    except ImportError as e:
        # This should never happen in practice, but handle gracefully
        import sys

        print(f"Warning: Could not register RequestsFetch: {e}", file=sys.stderr)

    # HttpxFetch (optional - depends on httpx package)
    try:
        from .implementations.httpx import HttpxFetch

        register_fetch("httpx", HttpxFetch)
    except ImportError:
        # httpx not installed, skip
        pass

    # CurlFetch (optional - depends on pycurl package)
    try:
        from .implementations.curl import CurlFetch

        register_fetch("curl", CurlFetch)
    except ImportError:
        # pycurl not installed, skip
        pass


# Auto-register on import
try:
    register_builtin_fetches()
except Exception:
    # Prevent import errors if something goes wrong during registration
    pass
