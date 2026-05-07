# Summary: Fetch vs. Unearth - Design Validation

**Date:** 2026-05-07
**Status:** ✅ Design validated against proven reference implementation

---

## Key Finding

✅ **Our fetch implementation successfully adopts unearth's proven Protocol-based design
while adding conda-specific enhancements.**

The core architectural insight from unearth - using `typing.Protocol` for a common HTTP
interface - provides confidence that our approach is sound.

---

## At a Glance

| Aspect | Unearth | Ours | Status |
|--------|---------|------|--------|
| **Protocol-based** | ✅ Yes | ✅ Yes | ✅ Validated |
| **No base classes** | ✅ Yes | ✅ Yes | ✅ Validated |
| **Requests wrapper** | ✅ Yes | ✅ Yes | ✅ Validated |
| **Registry pattern** | ✅ Yes | ✅ Yes | ✅ Validated |
| **Auth handlers** | ✅ Yes | ✅ Yes | ✅ Validated |
| **Httpx support** | ✅ Full | ~ Skeleton | ✅ On roadmap |
| **Exception mapping** | ~ Minimal | ✅ Explicit | ⭐ Enhanced |
| **File downloads** | ✗ No | ✅ Yes | ⭐ Added |
| **Progress tracking** | ✗ No | ✅ Yes | ⭐ Added |
| **Multiplexing** | ✗ No | ✅ Protocol | ⭐ Added |
| **Auth URL resolution** | ✗ No | ✅ Yes | ⭐ Added |
| **Conda integration** | ✗ N/A | ✅ Yes | ⭐ Added |

---

## Design Patterns Validated

### 1. Protocol-Based Abstraction ✅
**Pattern:** Use `typing.Protocol` for duck typing instead of ABC

**Unearth:**
```python
@runtime_checkable
class Fetcher(Protocol):
    def head(self, url: str, **kwargs) -> Response: ...
    def get(self, url: str, **kwargs) -> Response: ...
```

**Ours:**
```python
@runtime_checkable
class Fetch(Protocol):
    def head(self, url: str, **kwargs: Any) -> FetchResponse: ...
    def get(self, url: str, stream: bool = False, **kwargs: Any) -> FetchResponse: ...
    def get_file(
        self, url: str, fileobj: IO[bytes], progress_callback=None, **kwargs
    ) -> None: ...
```

**Verdict:** ✅ Same pattern, we added domain-specific methods

---

### 2. Requests Wrapper ✅
**Pattern:** Direct wrapper around `requests.Session` for zero overhead

**Unearth:**
```python
class RequestsFetcher:
    def __init__(self, session=None):
        self.session = session or Session()

    def get(self, url, **kwargs):
        return self.session.get(url, **kwargs)
```

**Ours:**
```python
class RequestsFetch:
    def __init__(self, session: Session | None = None):
        self.session = session or get_session()

    def get(self, url: str, stream: bool = False, **kwargs: Any) -> RequestsResponse:
        resp = self.session.get(url, stream=stream, **kwargs)
        return RequestsResponse(resp, request_url=url)
```

**Verdict:** ✅ Same pattern, we wrapped response + added error handling

---

### 3. Registry Pattern ✅
**Pattern:** Global registry for pluggable implementations

**Unearth:**
```python
_FETCHERS = {}


def get_fetcher(name="requests"):
    return _FETCHERS[name]()
```

**Ours:**
```python
_FETCHES = {}


def get_fetch(name: str | None = None) -> Fetch:
    if name is None:
        name = os.environ.get("CONDA_FETCH", "requests")
    return _FETCHES[name]()
```

**Verdict:** ✅ Same pattern, we added env var override + connection pooling

---

### 4. Exception Handling ✅
**Pattern:** Map library-specific exceptions to unified hierarchy

**Unearth:** Likely implicit/minimal

**Ours:**
```python
def map_requests_exception(exc: Exception) -> FetchException:
    if isinstance(exc, requests.Timeout):
        return FetchTimeout(str(exc))
    elif isinstance(exc, requests.ConnectionError):
        return FetchConnectionError(str(exc))
    # ... explicit mapping ...
    return FetchException(f"Unknown error: {exc}")
```

**Verdict:** ⭐ We made this explicit and comprehensive

---

### 5. Authentication ✅
**Pattern:** Auth as a protocol, flexible and composable

**Unearth:**
```python
@runtime_checkable
class Auth(Protocol):
    def __call__(self, request): ...
```

**Ours:**
```python
@runtime_checkable
class AuthHandler(Protocol):
    def apply(self, request: FetchRequest) -> FetchRequest: ...
    def handle_challenge(self, response: FetchResponse) -> bool: ...


class BasicAuthHandler:
    def apply(self, request: FetchRequest) -> FetchRequest: ...


class BearerTokenAuthHandler:
    def apply(self, request: FetchRequest) -> FetchRequest: ...
```

**Verdict:** ✅ Same pattern, we added concrete implementations + handle_challenge

---

## Enhancements Beyond Unearth

### 1. Explicit Request Representation ⭐
**Unearth:** Implicit (URL + **kwargs)
**Ours:** Explicit (FetchRequest dataclass)

**Benefit:** Type safety, IDE support, plugin integration

```python
@dataclass
class FetchRequest:
    url: str
    method: str = "GET"
    headers: dict[str, str] | None = None
    auth: AuthHandler | None = None
    timeout: tuple[float, float] | None = None
    verify: bool | str = True
    # ... 10+ more parameters ...
```

---

### 2. File Download API ⭐
**Unearth:** Not in base protocol
**Ours:** Full get_file() implementation

**Benefit:** Conda-specific pattern (DirectDownloadAdapter, progress)

```python
def get_file(
    self,
    url: str,
    fileobj: IO[bytes],
    progress_callback: Callable[[int, int], None] | None = None,
    **kwargs: Any,
) -> None:
    # Try DirectDownloadAdapter first
    adapter = self.session.get_adapter(url)
    if hasattr(adapter, "direct_download"):
        adapter.direct_download(url, fileobj, progress_callback)
        return

    # Fallback: streaming download
    resp = self.session.get(url, stream=True, **kwargs)
    # ... stream to file with progress reporting ...
```

---

### 3. Unified Exception Hierarchy ⭐
**Unearth:** Library-specific exceptions
**Ours:** Unified 7-type hierarchy

**Benefit:** Consistent error handling, better debugging

```
FetchException (base)
├── FetchConnectionError
├── FetchTimeout
├── FetchSSLError
├── FetchProxyError
├── FetchHTTPError
├── FetchRedirectError
└── (others)
```

---

### 4. Multiplexer Protocol ⭐
**Unearth:** Not present
**Ours:** FetchMultiplexer for concurrent requests

**Benefit:** Foundation for HTTP/2 multiplexing and curl integration

```python
class FetchMultiplexer(Fetch, Protocol):
    def queue_fetch(self, request: FetchRequest) -> int: ...
    def get_next_response(self, timeout: float | None = None) -> FetchResponseEvent: ...
    def cancel_all(self) -> None: ...
```

---

### 5. URL-Based Auth Resolution ⭐
**Unearth:** Generic auth handlers
**Ours:** ChannelAuthResolver for conda's channel pattern

**Benefit:** Deep conda integration, URL-to-auth mapping

```python
class ChannelAuthResolver:
    def get_auth(self, url: str) -> AuthHandler | None:
        if url in self._cache:
            return self._cache[url]
        auth = self._resolve_auth_from_plugins(url)
        self._cache[url] = auth
        return auth
```

---

### 6. Connection Pooling ⭐
**Unearth:** Per-request instances
**Ours:** get_fetch_cached() for session reuse

**Benefit:** Connection pooling, better performance

```python
def get_fetch_cached(name: str | None = None) -> Fetch:
    """Get or create a cached Fetch instance."""
    global _current_fetch
    if _current_fetch is not None:
        return _current_fetch
    _current_fetch = get_fetch(name)
    return _current_fetch
```

---

### 7. Environment Variable Override ⭐
**Unearth:** Via code only
**Ours:** CONDA_FETCH env var for testing

**Benefit:** Easy testing, runtime selection

```python
name = os.environ.get("CONDA_FETCH", "requests")
# Can override: CONDA_FETCH=httpx conda install numpy
```

---

### 8. Structured Error Context ⭐
**Unearth:** Standard exceptions
**Ours:** FetchErrorContext dataclass

**Benefit:** Better logging and debugging

```python
@dataclass
class FetchErrorContext:
    request: FetchRequest | None = None
    response: Any = None
    original_exception: Exception | None = None
    library_name: str | None = None
    retry_count: int = 0
    elapsed_time: float | None = None
```

---

## What We Learned from Unearth

### ✅ Principles to Keep
1. **Protocol > ABC** - Flexibility without coupling
2. **Duck typing** - Implementations are standalone
3. **Direct wrapping** - Zero-overhead adapters
4. **Registry pattern** - Easy discovery and registration
5. **Graceful degradation** - Skip missing libraries

### ⚠️ Where We Diverged (By Design)
1. **Request representation** - Made explicit for plugins
2. **Exception handling** - Made systematic for debugging
3. **Auth system** - Added conda-specific resolver
4. **File operations** - Added for conda's patterns
5. **Concurrency** - Added for future scalability

### 🚀 Proof Points
- ✅ Protocol pattern proven by unearth's success
- ✅ Wrapper pattern proven by unearth's requests implementation
- ✅ Registry pattern proven by unearth's plugin system
- ✅ Our additions are orthogonal (don't break compatibility)

---

## Compatibility Assessment

### Forward Compatibility with Unearth
✅ If unearth adds features, we can adopt them:
- New auth methods → Add to AuthHandler protocol
- New HTTP methods → Extend Fetch protocol
- New response properties → Extend FetchResponse protocol

### Backward Compatibility with Conda
✅ Our additions don't break unearth's patterns:
- Still protocol-based
- Still wrapper around requests
- Still registry-based discovery
- Still auth as protocol

---

## Risk Assessment

### Low Risk (Proven Patterns)
- ✅ Protocol-based design (unearth uses it)
- ✅ Requests wrapper (unearth does this)
- ✅ Registry pattern (unearth does this)
- ✅ Auth protocol (unearth does this)

### Medium Risk (Our Additions)
- ⚠️ FetchRequest dataclass (more explicit than unearth)
- ⚠️ Exception mapping (more systematic than unearth)
- ⚠️ File downloads (not in unearth, but conda-specific)

### Mitigation
- Follow unearth patterns closely for core
- Keep conda extensions in separate modules
- Maintain clear separation of concerns
- Good test coverage for new features

---

## Next Steps

### 1. Use This Validation ✅
- Reference unearth's proven approach
- Link to https://github.com/pypa/unearth in code
- Follow their design philosophy

### 2. Before Phase 1a
- Answer 15 design questions in OPERATOR.md
- Review with conda maintainers
- Get sign-off on enhancements

### 3. During Phase 1a
- Implement RequestsFetch (mostly done)
- Add comprehensive tests
- Integrate with download.py
- Document decisions

### 4. Future Phases
- Monitor unearth updates
- Adopt new patterns if they emerge
- Keep compatibility with unearth's registry
- Consider shared code if beneficial

---

## Conclusion

✅ **Our design is sound and validates against unearth's proven approach.**

We've successfully:
1. Adopted unearth's Protocol-based pattern ✅
2. Implemented the same wrapper/registry/auth architecture ✅
3. Enhanced it with conda-specific features ✅
4. Maintained compatibility and flexibility ✅

**Ready to proceed with Phase 1a implementation.**

---

## References

- **Unearth:** https://github.com/pypa/unearth
- **Unearth Fetcher Base:** https://github.com/pypa/unearth/blob/main/src/unearth/fetchers/base.py
- **Our Implementation:** conda/gateways/fetch/
- **Design Documents:** PLUGGABLE_REQUESTS_*.md
- **Design Questions:** OPERATOR.md
- **Code Comparison:** UNEARTH_CODE_COMPARISON.md
- **Conceptual Comparison:** COMPARISON_WITH_UNEARTH.md

---

*Comparison created: 2026-05-07*
*Status: ✅ Validation complete*
