# Copyright (C) 2012 Anaconda, Inc
# SPDX-License-Identifier: BSD-3-Clause
"""Authentication handlers for fetch requests.

Provides AuthHandler implementations (Basic, Bearer token, etc.) and integration
with conda's plugin system for custom auth via ChannelAuthResolver.
"""

from __future__ import annotations

from base64 import b64encode
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .request import FetchRequest
    from .types import AuthHandler


class BasicAuthHandler:
    """HTTP Basic Authentication (RFC 7617).

    Encodes username:password in Base64 and adds Authorization header.
    """

    def __init__(self, username: str, password: str):
        """Initialize with credentials.

        Args:
            username: Username.
            password: Password.
        """
        self.username = username
        self.password = password

    def apply(self, request: FetchRequest) -> FetchRequest:
        """Add Basic auth header to request.

        Args:
            request: FetchRequest to augment.

        Returns:
            Modified FetchRequest with Authorization header.
        """
        # Format: Authorization: Basic base64(username:password)
        credentials = f"{self.username}:{self.password}"
        encoded = b64encode(credentials.encode("utf-8")).decode("ascii")

        if request.headers is None:
            request.headers = {}
        request.headers["Authorization"] = f"Basic {encoded}"

        return request

    def handle_challenge(self, response) -> bool:
        """Basic auth doesn't handle 401 challenges (credentials are known)."""
        return False


class BearerTokenAuthHandler:
    """Bearer token authentication (RFC 6750).

    Adds Authorization: Bearer <token> header.
    Useful for API tokens, Anaconda tokens, etc.
    """

    def __init__(self, token: str):
        """Initialize with bearer token.

        Args:
            token: Bearer token (e.g., Anaconda Cloud token).
        """
        self.token = token

    def apply(self, request: FetchRequest) -> FetchRequest:
        """Add Bearer token to request.

        Args:
            request: FetchRequest to augment.

        Returns:
            Modified FetchRequest with Authorization header.
        """
        if request.headers is None:
            request.headers = {}
        request.headers["Authorization"] = f"Bearer {self.token}"

        return request

    def handle_challenge(self, response) -> bool:
        """Bearer tokens are static; can't refresh on 401."""
        return False


class ChannelAuthResolver:
    """Maps URLs to appropriate AuthHandler instances.

    Integrates with conda's plugin system to resolve authentication per URL/channel.
    Maintains a cache of resolved auth handlers to avoid repeated lookups.

    TODO: Implement integration with PluginManager and conda's auth plugins.
    """

    def __init__(self):
        """Initialize resolver and load auth plugins."""
        self._cache: dict[str, AuthHandler | None] = {}
        self._load_plugins()

    def _load_plugins(self) -> None:
        """Load ChannelAuthBase plugins from conda plugin system.

        TODO: Implement this using conda's PluginManager.
              Should call pm.hook.conda_auth_handler() and register handlers.
        """
        # PLACEHOLDER: To be implemented
        pass

    def get_auth(self, url: str) -> AuthHandler | None:
        """Resolve auth handler for a given URL.

        Checks cache first, then queries plugins if needed.

        Args:
            url: URL to find auth handler for.

        Returns:
            AuthHandler if one is registered for this URL, None otherwise.
        """
        # Check cache
        if url in self._cache:
            return self._cache[url]

        # TODO: Query plugins for matching auth
        auth = self._resolve_auth_from_plugins(url)

        # Cache result (including None for "no auth")
        self._cache[url] = auth
        return auth

    def _resolve_auth_from_plugins(self, url: str) -> AuthHandler | None:
        """Query plugins to find auth handler for URL.

        TODO: Implement using conda.plugins.PluginManager.
              Should:
              1. Extract channel/domain from URL
              2. Query conda_auth_handler() hook
              3. Match against URL prefix or channel name
              4. Return first matching handler
        """
        # PLACEHOLDER: To be implemented
        return None

    def apply(self, request: FetchRequest) -> FetchRequest:
        """Apply authentication to a request based on its URL.

        Args:
            request: FetchRequest to augment.

        Returns:
            Modified FetchRequest with auth applied.
        """
        auth = self.get_auth(request.url)
        if auth:
            request = auth.apply(request)
        return request

    def clear_cache(self) -> None:
        """Clear the auth handler cache.

        Useful if auth settings change at runtime.
        """
        self._cache.clear()


# Singleton instance
_default_auth_resolver: ChannelAuthResolver | None = None


def get_default_auth_resolver() -> ChannelAuthResolver:
    """Get or create the default ChannelAuthResolver instance.

    Returns:
        ChannelAuthResolver singleton.
    """
    global _default_auth_resolver
    if _default_auth_resolver is None:
        _default_auth_resolver = ChannelAuthResolver()
    return _default_auth_resolver
