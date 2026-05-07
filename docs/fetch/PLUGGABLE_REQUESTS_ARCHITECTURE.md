# Pluggable Requests Architecture Diagram

## System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      CONDA CORE (Users)                         │
├─────────────────────────────────────────────────────────────────┤
│  • conda install, update                                        │
│  • repodata fetching                                            │
│  • package downloading                                          │
└────────────────────┬────────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────────┐
│              conda/gateways/connection (PUBLIC API)             │
├─────────────────────────────────────────────────────────────────┤
│  • get_session(url) — UNCHANGED (backward compat)               │
│  • download(url, target) — REFACTORED (uses fetch)            │
│  • CondaSession — THIN WRAPPER (optional)                       │
└────────────────────┬────────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────────┐
│         conda/gateways/fetch (NEW - INTERNAL API)             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ PROTOCOLS (typing.Protocol)                               │  │
│  ├──────────────────────────────────────────────────────────┤  │
│  │ • Fetch         — Main interface (get, head, get_file)  │  │
│  │ • FetchResponse — Response object (headers, content)    │  │
│  │ • AuthHandler     — Auth abstraction (apply, challenge)   │  │
│  │ • FetchMultiplexer — Concurrent requests (opt-in)      │  │
│  └──────────────────────────────────────────────────────────┘  │
│                            ▲                                    │
│                            │ implements                         │
│  ┌─────────────────────────┼──────────────────────────────────┐ │
│  │ IMPLEMENTATIONS         │                                   │ │
│  ├─────────────────────────┼──────────────────────────────────┤ │
│  │                         │                                   │ │
│  │  RequestsFetch ◄──────┘  ← Wraps existing Session        │ │
│  │  (builtin, default)         (zero-overhead adapter)        │ │
│  │                                                             │ │
│  │  HttpxFetch (optional)    ← HTTP/2 support               │ │
│  │  (separate: conda-httpx)      (future, separate package)   │ │
│  │                                                             │ │
│  │  CurlFetch (optional)     ← Multiplexing                 │ │
│  │  (separate: conda-curl)       (future, separate package)   │ │
│  │                                                             │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ SUPPORT MODULES                                           │  │
│  ├──────────────────────────────────────────────────────────┤  │
│  │ • request.py      — FetchRequest, exceptions              │  │
│  │ • response.py     — Response building, error mapping      │  │
│  │ • auth.py         — Auth handlers, Channel resolver       │  │
│  │ • registry.py     — Fetch discovery & registration      │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ API                                                        │  │
│  ├──────────────────────────────────────────────────────────┤  │
│  │ • get_fetch(name) → Fetch                             │  │
│  │ • set_fetch(name, fetch)                              │  │
│  │ • list_fetches()                                          │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────────┐
│          conda/plugins/ (EXISTING PLUGIN SYSTEM)                │
├─────────────────────────────────────────────────────────────────┤
│  • conda_auth_handler() — Auth plugins (unchanged)              │
│  • conda_request_headers() — Header plugins (unchanged)         │
│  • conda_fetch() — NEW: Fetch plugins (future)              │
└─────────────────────────────────────────────────────────────────┘
```

---

## Data Flow: Single File Download

```
User calls download(url, target_path)
         │
         ▼
conda/gateways/connection/download.py
         │
         ├─ create FetchRequest object
         │
         ▼
get_fetch()  ← Looks up registered fetch (default: RequestsFetch)
         │
         ▼
fetch.get_file(url, fileobj, progress_callback)
         │
         ├─ Try optimized path (if DirectDownloadAdapter)
         │  │
         │  └─▶ adapter.direct_download() → write to fileobj
         │
         └─ Fallback: streaming
            │
            ├─ fetch.get(url) → FetchResponse
            │
            ├─ validate status code
            │
            ├─ check md5/sha256 if available
            │
            └─ stream response.iter_bytes() to fileobj
                     │
                     ▼
              FileNotFoundException
              ChecksumMismatchError
              CondaHTTPError
              etc. (mapped from fetch exceptions)
```

---

## Data Flow: Multiplexed Downloads (Future)

```
User queues 1000 packages to download
         │
         ▼
for url in urls:
    fetch.queue_fetch(FetchRequest(url))  ← enqueue (non-blocking)
         │
         ├─ RequestsFetch: queues to thread pool
         ├─ HttpxFetch: queues to async task
         └─ CurlFetch: queues to curl multi handle
         │
         ▼
while True:
    event = fetch.get_next_response(timeout=1.0)
         │
         ├─ ProgressEvent → update progress bar
         ├─ ResponseEvent → process response
         └─ ErrorEvent → handle error
         │
    process_response(event)
         │
         └─ write to file, verify checksum, etc.


Response events can arrive out of order → no head-of-line blocking!
HTTP/2 multiplexing on single connection → reduced latency.
Multiple TCP connections also possible → better bandwidth utilization.
```

---

## Session vs. Fetch: Migration Pattern

### Phase 1a (Current → Transition)

```python
# OLD CODE (still works)
from conda.gateways.connection import get_session

session = get_session("https://conda.anaconda.org")
resp = session.get("https://conda.anaconda.org/conda/packages.json")
content = resp.content

# Internally (transparent):
# Session.__init__() wraps a fetch
# session.get() delegates to _fetch.get()
```

### Phase 1b+ (After stabilization)

```python
# NEW RECOMMENDED CODE
from conda.gateways.fetch import get_fetch

fetch = get_fetch()  # or get_fetch("httpx")
resp = fetch.get("https://conda.anaconda.org/conda/packages.json")
content = resp.content

# Direct usage; no Session involved
# Can swap fetch without changing calling code
```

---

## Error Handling: Exception Mapping

```
HTTP Library (requests, httpx, curl, etc.)
         │
         ├─ requests.RequestException
         │  ├─ requests.ConnectionError
         │  ├─ requests.Timeout
         │  ├─ requests.HTTPError
         │  └─ ...
         │
         ├─ httpx.NetworkError
         ├─ httpx.TimeoutException
         ├─ httpx.HTTPStatusError
         └─ ...
         │
         ▼
FetchException (unified abstraction)
         │
         ├─ FetchConnectionError
         ├─ FetchTimeout
         ├─ FetchSSLError
         ├─ FetchHTTPError
         └─ ...
         │
         ▼
CondaError (existing conda exceptions)
         │
         ├─ CondaHTTPError
         ├─ CondaSSLError
         ├─ OfflineError
         ├─ ProxyError
         └─ ...
```

### Mapping (fetch/response.py)

```python
def map_to_conda_error(error: FetchException, context_url: str) -> CondaError:
    """Translate fetch exception to conda exception."""

    if isinstance(error, FetchHTTPError):
        if error.response.status_code in (401, 403):
            return AuthenticationError(...)
        elif error.response.status_code == 404:
            return BasicClobberError(...)
        else:
            return CondaHTTPError(...)

    elif isinstance(error, FetchSSLError):
        return CondaSSLError(...)

    elif isinstance(error, FetchConnectionError):
        if "Network unreachable" in str(error):
            return OfflineError(...)
        else:
            return ProxyError(...)

    # ... more mappings ...
```

---

## Module Import Tree

```
conda/gateways/fetch/
├── __init__.py
│   └─ from .types import Fetch, FetchResponse, ...
│   └─ from .registry import get_fetch, set_fetch
│
├── types.py (no internal deps)
│   └─ Protocols: Fetch, FetchResponse, AuthHandler, FetchMultiplexer
│
├── request.py (depends: none)
│   └─ FetchRequest, FetchException hierarchy
│
├── response.py (depends: types, request)
│   └─ Exception mapping, response building
│
├── auth.py (depends: types, request)
│   └─ AuthHandler protocol, implementations
│   └─ ChannelAuthResolver (plugin integration)
│
├── registry.py (depends: all above)
│   └─ get_fetch(), set_fetch(), list_fetches()
│   └─ Lazy loading of implementations
│
└── implementations/
    ├── requests.py (depends: types, response, auth)
    │   └─ RequestsFetch wrapper
    │   └─ RequestsResponse adapter
    │
    ├── httpx.py (FUTURE - separate package)
    │   └─ HttpxFetch (if httpx is installed)
    │
    └── curl.py (FUTURE - separate package)
        └─ CurlFetch (if pycurl is installed)

conda/gateways/connection/
├── __init__.py (re-exports for compatibility)
├── session.py (modified: thin wrapper)
├── download.py (modified: uses fetch)
└── adapters/ (unchanged)
```

---

## Configuration Options

### Environment Variables

```bash
# Select fetch at runtime
export CONDA_FETCH=httpx
conda install numpy

# Debug fetch operations
export CONDA_FETCH_DEBUG=1
export CONDA_FETCH_LOG_LEVEL=DEBUG

# Override default auth
export CONDA_TOKEN=...
```

### Configuration File (~/.condarc)

```yaml
# Fetch selection (when multiple available)
fetch: httpx

# Fallback chain (try each in order until one is available)
fetch_chain:
  - httpx
  - requests

# HTTP/2 specific options
http2_enabled: true
max_multiplexed_streams: 10

# Request tuning
request_timeout: 30
read_timeout: 60
```

---

## Feature Matrix: Fetch Comparison

| Feature | RequestsFetch | HttpxFetch | CurlFetch |
|---------|---|---|---|
| **HTTP/1.1** | ✓ | ✓ | ✓ |
| **HTTP/2** | ✗ | ✓ | ✓ |
| **HTTP/3** | ✗ | ✓ (future) | ✓ |
| **Streaming** | ✓ | ✓ | ✓ |
| **Direct download** | ✓ | ✓ | ✓ |
| **Multiplexing** | ✗ | ✓ (async) | ✓ (curl multi) |
| **Auth (Basic)** | ✓ | ✓ | ✓ |
| **Auth (Token)** | ✓ | ✓ | ✓ |
| **Proxies** | ✓ | ✓ | ✓ |
| **SSL/TLS** | ✓ | ✓ | ✓ |
| **Retries** | ✓ (urllib3) | ✓ | ✓ (curl) |
| **Dependency weight** | Light (urllib3) | Medium (httpx) | Medium (pycurl) |
| **Maturity** | Mature | Stable | Mature |

---

## Plugin Extension Points

### 1. Custom Fetch

```python
# plugins/custom_http_fetch.py

from conda.gateways.fetch import Fetch, FetchResponse
from conda.plugins import hookimpl


class MyFetch(Fetch):
    """Custom implementation using any HTTP library."""

    def get(self, url, **kwargs): ...


@hookimpl
def conda_fetch():
    return MyFetch
```

**Discovery:** Conda plugin manager finds `MyFetch` and registers it automatically.

### 2. Custom Auth Handler

```python
# plugins/custom_auth.py

from conda.gateways.fetch import AuthHandler
from conda.plugins import hookimpl


class OAuth2Handler(AuthHandler):
    def apply(self, request):
        request.headers["Authorization"] = f"Bearer {self.token}"
        return request

    def handle_challenge(self, response):
        if response.status_code == 401:
            self.refresh_token()
            return True
        return False


@hookimpl
def conda_auth_handler():
    return OAuth2Handler
```

**Integration:** ChannelAuthResolver automatically uses registered handlers.

### 3. Request Header Modifications

```python
# UNCHANGED - existing plugins continue to work


@hookimpl
def conda_request_headers(host, path):
    if host == "mycompany.com":
        return {"X-Company-Auth": get_auth()}
    return {}
```

---

## Testing Strategy Overview

### Unit Tests

```
tests/gateways/fetch/
├── test_fetch_protocol.py
│   ├─ test_fetch_protocol_compliance
│   ├─ test_fetch_response_protocol_compliance
│   └─ test_all_implementations_match_protocol
│
├── test_requests_fetch.py
│   ├─ test_basic_get_request
│   ├─ test_streaming_response
│   ├─ test_direct_download
│   ├─ test_error_handling
│   └─ test_auth_application
│
├── test_auth.py
│   ├─ test_basic_auth_handler
│   ├─ test_token_auth_handler
│   ├─ test_channel_auth_resolver
│   └─ test_plugin_integration
│
├── test_response.py
│   ├─ test_error_mapping
│   ├─ test_status_codes
│   └─ test_exception_hierarchy
│
└── test_registry.py
    ├─ test_get_fetch_default
    ├─ test_set_fetch
    └─ test_env_var_override
```

### Integration Tests

```
tests/gateways/test_connection.py (UPDATED)
├─ test_download_with_progress
├─ test_chunked_transfer_encoding
├─ test_redirect_handling
├─ test_authentication_flows
├─ test_proxy_support
├─ test_s3_adapter_still_works
├─ test_ftp_adapter_still_works
└─ test_backward_compatibility_with_session

tests/core/index/ (UPDATED)
├─ test_repodata_fetch_with_fetch
└─ test_index_update
```

### Performance Tests

```
benchmarks/fetch_benchmark.py
├─ compare_request_vs_fetch (should be same)
├─ measure_auth_overhead
└─ measure_parallel_downloads (future: multiplexing)
```

---

## Rollout Strategy

### Release Schedule

| Version | Action | Notes |
|---------|--------|-------|
| v26.4 | Introduce fetch module | Non-public internal API |
| v27.3 | Mark Session as "pending deprecation" | Grace period for users |
| v28.1 | Continue grace period | 2+ regular releases |
| v28.9 | Mark as "deprecated" | Direct warnings on use |
| v29.3 | Consider removal (optional) | Or stabilize as dual API |

### Breakage Prevention

✓ RequestsFetch is zero-overhead wrapper around existing Session
✓ No changes to download.py's external interface
✓ CondaSession remains unchanged (optional: thin wrapper)
✓ All plugin APIs unchanged (auth, headers)
✓ Backward compatibility maintained for ≥2 releases before any removal

---

## Quick Start for Developers

### Run Existing Tests
```bash
pytest tests/gateways/ -v
pytest tests/gateways/fetch/ -v  # New tests only
```

### Create a Custom Fetch
1. Implement `Fetch` protocol (get, head, get_file methods)
2. Wrap response in `FetchResponse`-compatible object
3. Map exceptions to `FetchException` hierarchy
4. Register via plugin hook: `conda_fetch()`

### Debug
```bash
export CONDA_FETCH=requests  # Force default
export CONDA_FETCH_DEBUG=1   # Enable debug logs
```

---

End of Architecture Document
