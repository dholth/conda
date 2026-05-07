# Quick Start: Implementing Pluggable Requests

## Phase 1a: RequestsFetch (Foundation)

### Checklist

#### Step 1: Create Module Structure
```bash
mkdir -p conda/gateways/fetch/implementations
touch conda/gateways/fetch/__init__.py
touch conda/gateways/fetch/types.py
touch conda/gateways/fetch/request.py
touch conda/gateways/fetch/response.py
touch conda/gateways/fetch/auth.py
touch conda/gateways/fetch/registry.py
touch conda/gateways/fetch/implementations/__init__.py
touch conda/gateways/fetch/implementations/requests.py
mkdir -p tests/gateways/fetch
touch tests/gateways/fetch/__init__.py
```

#### Step 2: Define Protocols (types.py)
- [ ] Write `Fetch` protocol with `get()`, `head()`, `get_file()` methods
- [ ] Write `FetchResponse` protocol with properties and methods
- [ ] Write `AuthHandler` protocol
- [ ] Add docstrings and type hints
- [ ] Document thread-safety assumptions

**Key:** Use `@runtime_checkable` to allow duck typing

#### Step 3: Define Request/Response Types (request.py, response.py)
- [ ] Create `FetchRequest` dataclass
- [ ] Create exception hierarchy:
  - `FetchException` (base)
  - `FetchConnectionError`
  - `FetchTimeout`
  - `FetchSSLError`
  - `FetchHTTPError`
  - `FetchProxyError`
- [ ] Map conda exceptions to fetch exceptions
- [ ] Write tests for exception hierarchy

#### Step 4: Implement RequestsFetch (implementations/requests.py)
```python
class RequestsFetch(Fetch):
    def __init__(self, session=None):
        self.session = session or get_session()

    def get(self, url: str, **kwargs) -> FetchResponse:
        resp = self.session.get(url, **kwargs)
        return RequestsResponse(resp)

    def head(self, url: str, **kwargs) -> FetchResponse:
        resp = self.session.head(url, **kwargs)
        return RequestsResponse(resp)

    def get_file(self, url: str, fileobj, progress_callback=None, **kwargs):
        # Try direct download if available
        adapter = self.session.get_adapter(url)
        if isinstance(adapter, DirectDownloadAdapter):
            adapter.direct_download(url, fileobj, progress_callback)
        else:
            # Stream fallback
            resp = self.session.get(url, stream=True, **kwargs)
            resp.raise_for_status()
            self._stream_to_file(resp, fileobj, progress_callback)


class RequestsResponse(FetchResponse):
    def __init__(self, response: Response):
        self._response = response

    @property
    def status_code(self) -> int:
        return self._response.status_code

    @property
    def headers(self) -> dict:
        return dict(self._response.headers)

    @property
    def content(self) -> bytes:
        # Raise if streaming
        if not self._response.raw.isclosed():
            raise RuntimeError("Cannot read content from streaming response")
        return self._response.content

    def iter_bytes(self, chunk_size: int = 8192):
        return self._response.iter_content(chunk_size)

    def raise_for_status(self) -> None:
        try:
            self._response.raise_for_status()
        except requests.HTTPError as e:
            raise FetchHTTPError(str(e), response=self)
```

- [ ] Implement all protocol methods
- [ ] Handle edge cases (streaming, error conditions)
- [ ] Write comprehensive tests

#### Step 5: Implement Registry (registry.py)
```python
_FETCHES = {
    "requests": RequestsFetch,
}
_CURRENT_FETCH = None


def get_fetch(name: str | None = None) -> Fetch:
    """Get fetch by name (or env var, or default)."""
    if name is None:
        name = os.environ.get("CONDA_FETCH", "requests")

    if name not in _FETCHES:
        raise ValueError(f"Unknown fetch: {name}")

    return _FETCHES[name]()


def set_fetch(name: str, fetch_class: type[Fetch]) -> None:
    """Register a fetch."""
    _FETCHES[name] = fetch_class
```

- [ ] Implement get_fetch(), set_fetch(), list_fetches()
- [ ] Support env var override
- [ ] Write tests for discovery

#### Step 6: Implement Auth Support (auth.py)
```python
class ChannelAuthResolver(AuthHandler):
    """Map URLs to auth handlers using existing plugin system."""

    def __init__(self):
        self._cache = {}  # URL → AuthHandler
        self._load_plugins()

    def apply(self, request: FetchRequest) -> FetchRequest:
        auth = self._get_auth_for_url(request.url)
        if auth:
            request = auth.apply(request)
        return request

    def _load_plugins(self):
        """Load ChannelAuthBase plugins from conda plugin system."""
        pm = PluginManager.instance()
        for auth_handler in pm.hook.conda_auth_handler():
            # Register auth handlers
            pass
```

- [ ] Integrate with conda plugin system
- [ ] Support existing auth plugins
- [ ] Write tests for auth chain

#### Step 7: Create __init__.py
```python
# conda/gateways/fetch/__init__.py
from .types import Fetch, FetchResponse, FetchMultiplexer
from .request import (
    FetchRequest,
    FetchException,
    FetchHTTPError,
)  # ...
from .auth import AuthHandler
from .registry import get_fetch, set_fetch, list_fetches

__all__ = [
    "Fetch",
    "FetchResponse",
    "FetchRequest",
    "FetchException",
    "AuthHandler",
    "get_fetch",
    "set_fetch",
]
```

#### Step 8: Update download.py
- [ ] Replace `session = get_session(url)` with `fetcher = get_fetch()`
- [ ] Replace `session.get(url, stream=True)` with `fetcher.get(url)`
- [ ] Keep all error handling; just map exceptions
- [ ] Verify all existing tests still pass

**Before:**
```python
def download_inner(*args):
    session = get_session(url)
    resp = session.get(url, stream=True, timeout=timeout)
    resp.raise_for_status()  # requests.HTTPError
    for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
        fileobj.write(chunk)
```

**After:**
```python
def download_inner(*args):
    fetcher = get_fetch()
    try:
        fetcher.get_file(url, fileobj, progress_callback)
    except FetchHTTPError as e:
        raise maybe_raise(CondaHTTPError(*args)) from e
    except FetchSSLError as e:
        raise CondaSSLError(*args) from e
```

#### Step 9: Write Tests
- [ ] Test RequestsFetch compliance with protocol
- [ ] Test get(), head(), get_file()
- [ ] Test error handling and exception mapping
- [ ] Test auth integration
- [ ] Test compatibility with existing download.py tests
- [ ] Verify no regressions in test_connection.py

**Test coverage target: >90%**

```bash
pytest tests/gateways/fetch/ -v --cov=conda/gateways/fetch
pytest tests/gateways/test_connection.py -v  # Existing tests
```

#### Step 10: Update connection/__init__.py (Backward Compat)
```python
# Re-export fetch types for compatibility
from .fetch import (
    Fetch,
    FetchResponse,
)

__all__ = [
    "Session",
    "Fetch",
    "FetchResponse",
    # ... existing exports ...
]
```

#### Step 11: Documentation
- [ ] Add module docstrings
- [ ] Add method docstrings with examples
- [ ] Update dev guide
- [ ] Add FAQ section
- [ ] Create news/ changelog fragment

#### Step 12: Code Quality
- [ ] Run ruff format and check
- [ ] Run mypy type checking
- [ ] Run pytest with coverage
- [ ] Verify no import cycles

```bash
ruff format conda/gateways/fetch/
ruff check conda/gateways/fetch/
mypy conda/gateways/fetch/ --strict
pytest tests/gateways/fetch/ -v --cov
```

#### Step 13: PR Checklist
- [ ] Squash commits
- [ ] Update PR title to reference issue
- [ ] Add description (summary of changes, design decisions)
- [ ] Link to PLUGGABLE_REQUESTS.md in description
- [ ] Add "enhancement" label
- [ ] Request review from:
  - Network/gateways maintainer
  - Plugin system maintainer
  - Plugin auth expert (if available)

---

## Phase 1b: Additional Fetchs (Future)

### HttpxFetch (separate package: conda-httpx)

```python
# conda_httpx/__init__.py

from httpx import AsyncClient, Client
from conda.gateways.fetch import Fetch, FetchResponse


class HttpxFetch(Fetch):
    """HTTP/2-capable fetch using httpx."""

    def __init__(self, http2=True):
        self.client = Client(http2=http2)

    def get(self, url, **kwargs):
        resp = self.client.get(url, **kwargs)
        return HttpxResponse(resp)

    # ... etc ...


# Register with conda
def register():
    from conda.gateways.fetch import set_fetch

    set_fetch("httpx", HttpxFetch)
```

### CurlFetch (separate package: conda-curl)

```python
# conda_curl/__init__.py

import pycurl
from conda.gateways.fetch import Fetch, FetchMultiplexer


class CurlFetch(Fetch, FetchMultiplexer):
    """Curl-based fetch with HTTP/2 and multiplexing."""

    def __init__(self):
        self.multi = pycurl.CurlMulti()
        self._requests = {}

    def queue_fetch(self, request):
        """Queue a request (multiplexer mode)."""
        curl_handle = pycurl.Curl()
        # ... configure curl ...
        self.multi.add_handle(curl_handle)
        return id(curl_handle)

    def get_next_response(self, timeout=None):
        """Get next response or event."""
        # ... select from multi handles ...
        pass

    # ... etc ...
```

---

## Testing Template

### File: tests/gateways/fetch/test_requests_fetch.py

```python
import pytest
from conda.gateways.fetch import get_fetch, Fetch, FetchResponse
from conda.gateways.fetch.implementations.requests import RequestsFetch


def test_requests_fetch_implements_protocol():
    """Verify RequestsFetch implements Fetch protocol."""
    fetcher = RequestsFetch()
    assert isinstance(fetcher, Fetch)


def test_get_request_basic(httpbin):
    """Test basic GET request."""
    fetcher = get_fetch("requests")
    resp = fetcher.get(f"{httpbin}/get")
    assert resp.status_code == 200
    assert "headers" in resp.json()


def test_streaming_response(httpbin):
    """Test streaming large response."""
    fetcher = get_fetch("requests")
    resp = fetcher.get(f"{httpbin}/stream/100")

    chunks = []
    for chunk in resp.iter_bytes(chunk_size=256):
        chunks.append(chunk)

    assert len(chunks) > 0
    assert b"url" in b"".join(chunks)


def test_error_mapping(httpbin):
    """Test HTTP error mapping."""
    from conda.gateways.fetch import FetchHTTPError

    fetcher = get_fetch("requests")
    with pytest.raises(FetchHTTPError) as exc_info:
        resp = fetcher.get(f"{httpbin}/status/404")
        resp.raise_for_status()

    assert exc_info.value.response.status_code == 404


def test_auth_handler(httpbin):
    """Test auth handler integration."""
    from conda.gateways.fetch.auth import BasicAuthHandler

    fetcher = get_fetch("requests")
    # ... test auth ...


def test_backward_compat_with_session():
    """Verify RequestsFetch wraps Session correctly."""
    from conda.gateways.connection import get_session

    session = get_session()
    fetcher = RequestsFetch(session)

    # Both should work identically
    # ... test equivalence ...
```

---

## Common Issues & Troubleshooting

### Issue: Circular Imports

**Symptom:**
```
ImportError: cannot import name 'FetchRequest' from partially initialized module
```

**Fix:** Check import order in `__init__.py` files:
1. types.py (no internal deps)
2. request.py (depends: none)
3. response.py (depends: types, request)
4. auth.py (depends: types, request)
5. registry.py (depends: all above)
6. implementations/ (depends: all above)

### Issue: Protocol Not Recognized

**Symptom:**
```
AssertionError: not isinstance(fetcher, Fetch)
```

**Fix:** Ensure `@runtime_checkable` on protocol:
```python
from typing import Protocol, runtime_checkable


@runtime_checkable
class Fetch(Protocol): ...
```

### Issue: Exception Mapping Incomplete

**Symptom:**
```
AttributeError: FetchHTTPError has no attribute 'response'
```

**Fix:** Ensure all exceptions store necessary data:
```python
@dataclass
class FetchHTTPError(FetchException):
    message: str
    response: FetchResponse  # Must be present
```

### Issue: Auth Not Applied

**Symptom:**
```
403 Forbidden when accessing authenticated resource
```

**Fix:** Verify ChannelAuthResolver is called:
```python
auth_resolver = ChannelAuthResolver()
request = auth_resolver.apply(request)  # MUST call this
```

---

## Success Metrics

After Phase 1a, you should be able to:

✓ Create a custom Fetch and register it via registry
✓ Download files using the new fetch interface
✓ Use multiple fetchers interchangeably
✓ Run all existing conda tests without changes
✓ Switch fetchers with an env var: `CONDA_FETCH=httpx`
✓ See zero performance regression vs. current requests

---

## Resources

- **Implementation Plan:** `/Users/dholth/prog/conda/PLUGGABLE_REQUESTS_IMPLEMENTATION_PLAN.md`
- **Architecture:** `/Users/dholth/prog/conda/PLUGGABLE_REQUESTS_ARCHITECTURE.md`
- **Original Spec:** `/Users/dholth/prog/conda/PLUGGABLE_REQUESTS.md`
- **Unearth Source:** https://github.com/pypa/unearth/blob/main/src/unearth/fetchers/base.py
- **conda-httpx Reference:** https://github.com/dholth/conda-httpx
- **conda-libmamba-solver Shards:** https://github.com/conda/conda-libmamba-solver/blob/main/conda_libmamba_solver/shards_subset.py#L622

---

## Questions?

If blocked on any step:
1. Check the Architecture document for detailed component explanations
2. Reference unearth's implementation: https://github.com/pypa/unearth
3. Review conda-httpx for a working integration example
4. Ask in conda-dev issues or discussions

---

End of Quick Start Guide
