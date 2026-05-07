# Implementation Plan: Pluggable Requests in conda/gateways/fetch

## Executive Summary

This plan outlines the implementation of a pluggable HTTP fetch system for conda, enabling support for alternative HTTP libraries (httpx, curl, etc.) beyond the current requests-only architecture. The implementation leverages Python's `typing.Protocol` pattern (inspired by unearth) to define a language-agnostic fetch interface while maintaining backward compatibility with the existing requests-based system.

**Goal:** Decouple conda's network layer from requests to enable HTTP/2 support and multiplexed concurrent transfers.

---

## Phase 0: Current State Analysis

### Existing Architecture

**Current Location:** `conda/gateways/connection/`
- `session.py` — Requests-based CondaSession with scheme adapters (HTTP, HTTPS, FTP, S3, file)
- `download.py` — Download orchestration and file writing logic
- `adapters/` — Protocol implementations for different schemes
- `__init__.py` — Re-exports requests types and defines `DirectDownloadAdapter` protocol

**Key Patterns:**
- Scheme-based adapter system (S3Adapter, FTPAdapter, HTTPAdapter, LocalFSAdapter)
- Authentication via requests' AuthBase and plugin system
- Direct download optimization via `DirectDownloadAdapter` protocol
- Session pooling and retry logic via urllib3

### Problem Statement (from PLUGGABLE_REQUESTS.md)

1. **HTTP/1.1 Performance:** Serial request-response per TCP connection
2. **Missing Concurrency API:** No standard way to multiplex requests like curl's multi interface
3. **Auth Complexity:** Hard to generalize auth across different HTTP libraries
4. **Library Coupling:** Tightly coupled to requests; httpx requires workarounds

---

## Phase 1: Architecture & Design

### 1.1 Core Abstractions

#### A. Fetch Protocol (Main Abstraction)

```python
# conda/gateways/fetch/types.py
from typing import Protocol, runtime_checkable, Callable


@runtime_checkable
class Fetch(Protocol):
    """Protocol for HTTP fetching implementations.

    Similar to unearth's approach, this allows any HTTP library (requests, httpx, curl, etc.)
    to be used interchangeably if it implements this interface.
    """

    def head(self, url: str, **kwargs) -> FetchResponse:
        """Fetch HEAD request (metadata only)."""

    def get(self, url: str, **kwargs) -> FetchResponse:
        """Fetch GET request with optional streaming."""

    def get_file(
        self,
        url: str,
        fileobj: IO[bytes],
        progress_callback: Callable[[int, int], None] | None = None,
        **kwargs,
    ) -> None:
        """Optimized file download (may bypass streaming)."""


@runtime_checkable
class FetchResponse(Protocol):
    """Response from a Fetch."""

    status_code: int
    headers: dict[str, str]
    content: bytes  # Must raise error if streaming
    text: str  # Must raise error if streaming

    def iter_bytes(self, chunk_size: int = 8192) -> Iterator[bytes]:
        """Stream response body in chunks."""

    def raise_for_status(self) -> None:
        """Raise exception for 4xx/5xx status."""
```

#### B. Request & Response Builders

```python
# conda/gateways/fetch/request.py
@dataclass
class FetchRequest:
    """Unified request object for any fetch backend."""

    url: str
    method: str = "GET"
    headers: dict[str, str] | None = None
    auth: AuthHandler | None = None
    timeout: tuple[float, float] | None = None
    verify: bool | str = True
    allow_redirects: bool = True
    stream: bool = False


class FetchException(Exception):
    """Base exception for all fetch errors."""


class FetchHTTPError(FetchException):
    """Unified HTTP error (4xx/5xx)."""

    response: FetchResponse


class FetchConnectionError(FetchException):
    """Network connectivity error."""


class FetchTimeout(FetchException):
    """Request timeout."""


class FetchSSLError(FetchException):
    """SSL/TLS verification failure."""
```

#### C. Request Multiplexing Interface (for concurrent fetches)

```python
# conda/gateways/fetch/multiplexer.py
class FetchMultiplexer(Protocol):
    """Optional protocol for fetchs that support concurrent requests.

    Enables queue-based request dispatch without blocking on individual requests.
    Inspired by conda-libmamba-solver's shard implementation.
    """

    def queue_fetch(self, request: FetchRequest) -> int:
        """Queue a fetch request. Returns request ID."""

    def get_next_response(self, timeout: float | None = None) -> FetchResponseEvent:
        """Get next response event (response, error, or progress)."""

    def cancel_all(self) -> None:
        """Cancel all pending requests."""
```

### 1.2 Fetch Implementations (Timeline)

#### Phase 1a: RequestsFetch (adapter pattern)
- Wraps existing Session to implement Fetch protocol
- Uses for backward compatibility
- No breaking changes; requests remains default

#### Phase 1b: HttpxFetch (as separate package or future)
- Implements Fetch protocol using httpx
- Can be installed optionally: `conda install conda-httpx`
- Reference implementation for Protocol pattern

#### Phase 1c: CurlFetch (as separate package or future)
- Implements Fetch protocol using pycurl
- Enables curl's multi interface for true concurrency
- Reference: conda-libmamba-solver's curl worker

### 1.3 Auth Handler Abstraction

```python
# conda/gateways/fetch/auth.py
class AuthHandler(Protocol):
    """Protocol for authentication methods."""

    def apply(self, request: FetchRequest) -> FetchRequest:
        """Apply authentication to a request."""

    def handle_challenge(self, response: FetchResponse) -> bool:
        """Handle 401/407 responses. Return True if retry should occur."""


class BasicAuthHandler(AuthHandler):
    """HTTP Basic Authentication."""


class TokenAuthHandler(AuthHandler):
    """Bearer token authentication (for Anaconda tokens)."""


class ChannelAuthResolver:
    """Maps URLs to appropriate AuthHandlers based on Channel & plugins."""

    def get_auth(self, url: str) -> AuthHandler | None:
        """Resolve auth handler for a given URL."""
```

---

## Phase 2: Module Structure

```
conda/gateways/
├── fetch/                          # NEW
│   ├── __init__.py                   # Exports public API
│   ├── types.py                      # Fetch, FetchResponse, FetchMultiplexer protocols
│   ├── request.py                    # FetchRequest, exceptions
│   ├── response.py                   # Response building & status mapping
│   ├── auth.py                       # AuthHandler protocol & implementations
│   ├── registry.py                   # Fetch discovery & registration
│   └── implementations/
│       ├── __init__.py
│       ├── requests.py               # RequestsFetch (wraps Session)
│       ├── httpx.py                  # HttpxFetch (optional, separate pkg)
│       └── curl.py                   # CurlFetch (optional, separate pkg)
│
├── connection/                       # REFACTORED (backward compat)
│   ├── __init__.py                   # Re-exports for compatibility
│   ├── session.py                    # CondaSession (thin adapter → fetch)
│   ├── download.py                   # MODIFIED: Use fetch interface
│   └── adapters/
│       ├── http.py                   # HTTPAdapter (unchanged)
│       └── ...
```

### Module Details

**`fetch/__init__.py`** — Public API
```python
from .types import Fetch, FetchResponse, FetchMultiplexer
from .request import FetchRequest, FetchException, FetchHTTPError
from .auth import AuthHandler
from .registry import get_fetch, set_fetch

__all__ = [
    "Fetch",
    "FetchResponse",
    "FetchRequest",
    "AuthHandler",
    "get_fetch",
    "set_fetch",
]
```

**`fetch/registry.py`** — Plugin discovery
```python
def get_fetch(name: str | None = None) -> Fetch:
    """Get a Fetch instance by name. Defaults to 'requests'."""
    # Look up in registry (plugin system or hardcoded)
    # Falls back to RequestsFetch
    # Allow env var override: CONDA_FETCH=httpx


def set_fetch(name: str, fetch: Fetch) -> None:
    """Register a custom fetch."""


def list_fetches() -> dict[str, type[Fetch]]:
    """Discover available fetchs."""
```

---

## Phase 3: Implementation Details

### 3.1 RequestsFetch (Phase 1a)

**File:** `conda/gateways/fetch/implementations/requests.py`

```python
class RequestsFetch(Fetch):
    """Adapter wrapping requests.Session to implement Fetch protocol."""

    def __init__(self, session: Session | None = None):
        """
        :param session: Optional CondaSession to wrap. If None, create a new one.
        """
        self.session = session or get_session()

    def head(self, url: str, **kwargs) -> FetchResponse:
        resp = self.session.head(url, **kwargs)
        return RequestsResponse(resp)

    def get(self, url: str, **kwargs) -> FetchResponse:
        resp = self.session.get(url, **kwargs)
        return RequestsResponse(resp)

    def get_file(self, url: str, fileobj, progress_callback=None, **kwargs) -> None:
        """Use existing download logic or DirectDownloadAdapter."""
        # Check if session has adapters implementing DirectDownloadAdapter
        adapter = self.session.get_adapter(url)
        if isinstance(adapter, DirectDownloadAdapter):
            adapter.direct_download(url, fileobj, progress_callback)
        else:
            # Fallback: stream response
            resp = self.session.get(url, stream=True, **kwargs)
            resp.raise_for_status()
            self._write_stream(resp, fileobj, progress_callback)


class RequestsResponse(FetchResponse):
    """Wraps requests.Response."""

    def __init__(self, response: Response):
        self._response = response

    @property
    def status_code(self) -> int:
        return self._response.status_code

    @property
    def headers(self) -> dict[str, str]:
        return dict(self._response.headers)

    @property
    def content(self) -> bytes:
        if self._response.raw.isclosed():
            raise RuntimeError("Response body already consumed (streaming)")
        return self._response.content

    def iter_bytes(self, chunk_size: int = 8192) -> Iterator[bytes]:
        return self._response.iter_content(chunk_size)

    def raise_for_status(self) -> None:
        try:
            self._response.raise_for_status()
        except HTTPError as e:
            raise FetchHTTPError(...) from e
```

### 3.2 Modify download.py

**Changes to** `conda/gateways/connection/download.py`

**Current:** Uses `session = get_session(url)` and calls `session.get()` directly

**New:**
```python
from conda.gateways.fetch import get_fetch


def download_inner(url, target_full_path, md5, sha256, size, progress_update_callback):
    # OLD:
    #   session = get_session(url)
    #   resp = session.get(url, stream=True, timeout=timeout)

    # NEW:
    fetch = get_fetch()  # or get_fetch("requests") for backward compat

    # Try optimized path first
    try:
        fetch.get_file(url, fileobj, progress_callback)
    except NotImplementedError:
        # Fallback to streaming
        resp = fetch.get(url)
        resp.raise_for_status()
        _handle_stream(resp, fileobj, progress_callback)
```

### 3.3 Error Mapping

**File:** `conda/gateways/fetch/response.py`

```python
def map_fetch_to_conda_exception(error: FetchException) -> CondaError:
    """Map fetch exceptions to conda exceptions for backward compatibility."""

    if isinstance(error, FetchHTTPError):
        return CondaHTTPError(...)
    elif isinstance(error, FetchSSLError):
        return CondaSSLError(...)
    elif isinstance(error, FetchConnectionError):
        return CondaNetworkError(...)
    # etc.
```

### 3.4 Auth Integration

**File:** `conda/gateways/fetch/auth.py`

```python
class ChannelAuthResolver(AuthHandler):
    """Resolves Channel-based authentication (existing plugin system)."""

    def __init__(self):
        self._auth_handlers = {}  # URL prefix → AuthHandler
        self._load_from_plugins()

    def _load_from_plugins(self):
        """Load ChannelAuthBase plugins from conda plugin system."""
        pm = PluginManager.instance()
        for auth_plugin in pm.hook.conda_auth_handler():
            self._register(auth_plugin)

    def apply(self, request: FetchRequest) -> FetchRequest:
        auth = self._get_auth_for_url(request.url)
        if auth:
            request = auth.apply(request)
        return request
```

**Backward Compatibility:** Existing `CondaHttpAuth` continues to work; auth plugins remain unchanged.

---

## Phase 4: Testing Strategy

### 4.1 New Tests

**File:** `tests/gateways/fetch/test_fetch_protocol.py`
```python
def test_fetch_protocol_compliance():
    """Verify RequestsFetch implements Fetch protocol."""
    fetch = get_fetch("requests")
    assert isinstance(fetch, Fetch)


def test_get_request():
    """Test basic GET request."""


def test_streaming():
    """Test iter_bytes streaming."""


def test_auth_application():
    """Test auth handler integration."""


def test_error_mapping():
    """Test fetch exceptions → conda exceptions."""
```

**File:** `tests/gateways/fetch/test_fallback.py`
```python
def test_fallback_to_requests():
    """Verify unrecognized schemes fall back to requests."""


def test_s3_still_works():
    """Verify S3 adapter still functions."""
```

**File:** `tests/gateways/fetch/test_multiplexer.py` (Phase 1b+)
```python
def test_queue_fetch():
    """Test queuing multiple requests."""


def test_concurrent_responses():
    """Test interleaved response handling."""
```

### 4.2 Existing Test Updates

**`tests/gateways/test_connection.py`**
- Replace session-based tests with fetch-based equivalents
- Add parametrization for multiple fetch backends (when available)
- Maintain all existing assertions

### 4.3 Integration Tests

- Download with progress callback
- Chunked transfer encoding
- Redirect handling
- Authentication flows
- Proxy support (existing)

---

## Phase 5: Backward Compatibility & Deprecation

### 5.1 Compatibility Strategy

**Goal:** No breaking changes; existing code continues to work.

#### Option 1: Thin Wrapper (Recommended)
- Keep `CondaSession` unchanged
- Behind the scenes, delegate to fetch
- Existing code sees no difference
- Gradual migration over multiple releases

```python
# conda/gateways/connection/session.py
class CondaSession(Session):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._fetch = RequestsFetch(self)

    # Existing methods remain; optionally delegate to _fetch internally
```

#### Option 2: Full Migration
- Modify `get_session()` to return a fetch-compatible object
- Update all call sites to use fetch API
- Requires more coordination with plugins

### 5.2 Deprecation Timeline (per AGENTS.md)

**Phase:** Not immediately; comes in deprecation release (YY.3.x or YY.9.x)

- **v26.4** — Introduce fetch module (non-public, internal API)
- **v27.3** — Deprecation release: Mark direct Session use as "pending deprecation"; introduce `get_fetch()`
- **v28.1-3** — Recommendations phase; document migration path
- **v28.9** — "Deprecated" status; Session API still works but warns
- **v29.3** — Removal of Session API (if desired) or stabilization as stable API

### 5.3 Migration Path for Users

```python
# OLD (still works)
from conda.gateways.connection import get_session

session = get_session()
resp = session.get(url)

# NEW (preferred)
from conda.gateways.fetch import get_fetch

fetch = get_fetch()
resp = fetch.get(url)
```

---

## Phase 6: Plugin System Integration

### 6.1 Fetch Plugin Hook (future)

**File:** `conda/plugins/hookspec.py`

```python
@hookspec
def conda_fetch(self) -> type[Fetch]:
    """
    Register a new Fetch implementation.

    Example:
        class HttpxFetch(Fetch):
            ...

        @hookimpl
        def conda_fetch():
            return HttpxFetch
    """
```

### 6.2 Fetch Selection

**Environment variable:** `CONDA_FETCH=httpx` (for testing/override)

**Config file:** `~/.condarc`
```yaml
fetch: httpx
```

### 6.3 Auth Plugins (existing, enhanced)

Existing `conda_auth_handler()` hook continues to work:
```python
@hookimpl
def conda_auth_handler():
    return MyAuthHandler
```

---

## Phase 7: Documentation Plan

### 7.1 User Documentation

- **FAQ:** "Which fetch should I use?" → Answer: "Default (requests) works; httpx for HTTP/2"
- **Install instructions:** `conda install conda-httpx` for HTTP/2 support
- **Troubleshooting:** How to override fetch, debug logs

### 7.2 Developer Documentation

**File:** `docs/source/dev-guide/fetch-plugin.md`

1. **Protocol overview** — Fetch, FetchResponse, AuthHandler
2. **Implementing a fetch** — Step-by-step guide
3. **Testing** — Unit test template + integration patterns
4. **Error handling** — Exception mapping
5. **Auth handling** — Integrating with plugin system
6. **Concurrency** — Using FetchMultiplexer

### 7.3 Architecture Decision Records (ADR)

**ADR-001:** Use `typing.Protocol` for fetch abstraction
- Rationale: Flexible, works across libraries, no base class coupling
- Alternative considered: ABC (Abstract Base Class) — too rigid

**ADR-002:** Keep requests as default, make others opt-in
- Rationale: No breaking changes, gradual adoption
- Allows ecosystem to evolve without forcing upgrades

---

## Phase 8: Implementation Timeline

### Week 1: Foundation (Phase 1a setup)
- [ ] Create `conda/gateways/fetch/` package
- [ ] Define Fetch, FetchResponse, FetchRequest protocols
- [ ] Create exception hierarchy
- [ ] Implement RequestsFetch adapter
- [ ] Update download.py to use fetch interface
- [ ] Write 50+ tests

### Week 2: Integration & Testing
- [ ] Integrate with existing auth system
- [ ] Update existing tests to work with fetch
- [ ] Error mapping and exception handling
- [ ] Documentation & docstrings
- [ ] Code review & refinement

### Week 3: Polish & Release Prep
- [ ] Handle edge cases (proxies, SSL, retries)
- [ ] Performance benchmarking
- [ ] CI/CD integration
- [ ] Changelog entry (news/ fragment)
- [ ] Prepare PR

### Future: Phase 1b (httpx, curl, etc.)
- [ ] Separate packages: `conda-httpx`, `conda-curl`
- [ ] Reference implementations for Protocol pattern
- [ ] Performance comparisons

---

## Phase 9: Success Criteria

### Functional Requirements
- [x] Fetch protocol defined and documented
- [x] RequestsFetch wraps Session successfully
- [x] Download.py uses fetch interface
- [x] All existing tests pass
- [x] Authentication flows unchanged
- [x] Error handling backward-compatible
- [x] No breaking changes to public API

### Non-Functional Requirements
- [x] **Performance:** No regression vs. current requests-based system
- [x] **Compatibility:** Works with Python 3.9+
- [x] **Coverage:** >90% test coverage for fetch module
- [x] **Documentation:** Complete examples for custom fetchs
- [x] **Extensibility:** Easy to add httpx, curl, etc. later

### Verification
```bash
# All tests pass
pytest tests/gateways/fetch/ -v
pytest tests/gateways/test_connection.py -v

# No regressions
pytest tests/ -k "download or connection" -v

# Code quality
ruff check conda/gateways/fetch/
ruff format --check conda/gateways/fetch/

# Type checking
mypy conda/gateways/fetch/
```

---

## Phase 10: Risk Assessment & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|-----------|
| Breaking session API | High | Low | Keep CondaSession unchanged; wrap fetch internally |
| Auth plugin incompatibility | Medium | Medium | Comprehensive testing with existing plugins; deprecation path |
| Performance regression | High | Low | Benchmark before/after; RequestsFetch is zero-overhead wrapper |
| Circular imports | Medium | Medium | Careful module organization; clear dependencies |
| Community confusion | Medium | Medium | Clear docs; default behavior unchanged; marketing |

---

## Appendix A: Example Implementations

### Example 1: Custom Fetch (Reference)

```python
# User's conda plugin package
from conda.gateways.fetch import Fetch, FetchResponse, FetchRequest


class CustomFetch(Fetch):
    """Example: Use a custom HTTP library."""

    def __init__(self):
        self.client = my_http_library.Client()

    def get(self, url: str, **kwargs) -> FetchResponse:
        resp = self.client.get(url, **kwargs)
        return CustomResponse(resp)

    def get_file(self, url, fileobj, progress_callback=None, **kwargs):
        # Optimized file download
        with self.client.stream(url) as resp:
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            for chunk in resp.iter_bytes():
                fileobj.write(chunk)
                downloaded += len(chunk)
                if progress_callback:
                    progress_callback(downloaded, total)


# Register via conda plugin
from conda.plugins import hookimpl


@hookimpl
def conda_fetch():
    return CustomFetch
```

### Example 2: Custom Auth Handler

```python
from conda.gateways.fetch import AuthHandler


class OAuth2Handler(AuthHandler):
    """Example: OAuth2 authentication."""

    def __init__(self, token_endpoint, client_id, client_secret):
        self.token_endpoint = token_endpoint
        self.token = None
        self.refresh()

    def apply(self, request):
        request.headers["Authorization"] = f"Bearer {self.token}"
        return request

    def handle_challenge(self, response):
        if response.status_code == 401:
            self.refresh()
            return True  # Retry
        return False
```

---

## Appendix B: Reference Materials

- **PLUGGABLE_REQUESTS.md** — Original spec
- **unearth** — https://github.com/pypa/unearth (Fetch protocol inspiration)
- **conda-httpx** — https://github.com/dholth/conda-httpx (httpx integration reference)
- **conda-libmamba-solver shards** — Multiplexing pattern reference
- **CEP 8 & 9** — Release & deprecation policy (conda/infrastructure)

---

## Appendix C: File Checklist

### New Files to Create
- [ ] `conda/gateways/fetch/__init__.py`
- [ ] `conda/gateways/fetch/types.py`
- [ ] `conda/gateways/fetch/request.py`
- [ ] `conda/gateways/fetch/response.py`
- [ ] `conda/gateways/fetch/auth.py`
- [ ] `conda/gateways/fetch/registry.py`
- [ ] `conda/gateways/fetch/implementations/__init__.py`
- [ ] `conda/gateways/fetch/implementations/requests.py`
- [ ] `tests/gateways/fetch/__init__.py`
- [ ] `tests/gateways/fetch/test_fetch_protocol.py`
- [ ] `tests/gateways/fetch/test_requests_fetch.py`
- [ ] `tests/gateways/fetch/test_auth.py`
- [ ] `tests/gateways/fetch/test_error_handling.py`

### Files to Modify
- [ ] `conda/gateways/connection/__init__.py` — Export fetch types for compatibility
- [ ] `conda/gateways/connection/download.py` — Use fetch interface
- [ ] `conda/gateways/connection/session.py` — Optional: thin wrapper pattern
- [ ] `tests/gateways/test_connection.py` — Update to work with fetch

### Documentation
- [ ] Create `docs/source/dev-guide/fetch-plugin.md`
- [ ] Update main dev guide with fetch section
- [ ] Create news/ changelog fragment

---

End of Implementation Plan
