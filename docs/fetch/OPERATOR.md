# OPERATOR.md: Questions & Design Decisions for Fetch Implementation

This document lists open questions and design decisions that need clarification before
full implementation can proceed. Please address these before starting Phase 1a.

---

## High-Priority Questions

### Q1: Error Handling & Backward Compatibility

**Question:** How should we handle backward compatibility with existing conda exception
hierarchy during the transition?

**Context:**
- Current code uses `conda.gateways.connection.exceptions` (CondaHTTPError, CondaSSLError, etc.)
- We're introducing `conda.gateways.fetch.request` exceptions (FetchHTTPError, FetchSSLError, etc.)
- Existing code expects conda-specific exceptions, not generic fetch exceptions

**Options:**
1. **Wrapper approach**: In `download.py`, catch `FetchException` and immediately convert to `CondaError`
   - Pro: No breaking changes, keeps exception types familiar
   - Con: Adds translation layer, potential performance overhead

2. **Parallel approach**: Keep both exception hierarchies, let them coexist
   - Pro: Gradual migration possible
   - Con: Code duplication, confusing for developers

3. **Unified approach**: Replace conda exceptions with fetch exceptions everywhere
   - Pro: Single source of truth
   - Con: Breaking change, requires major migration

**Decision Needed:** Which approach? Or something else?

**Recommendation:** Suggest **Wrapper approach** - map in `response.py` and raise conda exceptions
at the boundary (download.py). Keep fetch exceptions internal to the module.

---

### Q2: Request/Response Implementation

**Question:** Should `FetchRequest` be a dataclass or a Protocol?

**Context:**
- Currently: `FetchRequest` is a dataclass (in request.py)
- Alternative: Make it a Protocol so implementations can use their own request types

**Options:**
1. **Dataclass** (current):
   - Pro: Concrete, easy to use, IDE support for fields
   - Con: Implementations must convert to/from library formats

2. **Protocol**:
   - Pro: Implementations can use native library request types
   - Con: Less concrete, harder to work with

**Decision Needed:** Keep dataclass or switch to Protocol?

**Recommendation:** Keep dataclass - it's simpler and implementations can easily wrap it.

---

### Q3: Session vs. Fetch in download.py

**Question:** How much of download.py should be refactored?

**Context:**
- `download.py` currently uses `get_session()` and Session methods directly
- Should we:
  a) Minimally refactor (just replace Session with Fetch)
  b) Fully refactor (rewrite download logic using Fetch abstractions)
  c) Gradually refactor (Phase 1a minimal, Phase 1b+ cleanup)

**Decision Needed:** Refactoring scope for Phase 1a?

**Recommendation:** Minimal refactoring (option a) - just replace Session with Fetch.
Full refactor can wait until Phases 1b/2 when we have working implementations.

---

### Q4: Direct Download Adapter Integration

**Question:** How should special adapters (S3Adapter, FTPAdapter) be handled?

**Context:**
- Current Session has scheme-specific adapters
- Each adapter might support `DirectDownloadAdapter` protocol for optimized downloads
- RequestsFetch needs to interact with these

**Questions:**
- Should RequestsFetch continue using existing adapters, or wrap them?
- How do we handle S3:// URLs which don't use standard HTTP?
- Should other fetches (httpx, curl) support these adapters?

**Decision Needed:** Integration strategy with existing adapter system?

**Recommendation:** RequestsFetch delegates to existing adapters (minimal change).
Future fetches can implement their own adapter patterns. Document this clearly.

---

### Q5: AuthHandler Integration with Conda Plugins

**Question:** How should `ChannelAuthResolver` integrate with conda's plugin system?

**Context:**
- Currently: ChannelAuthResolver is a placeholder with TODO comments
- Conda has: `PluginManager` and `conda_auth_handler` hooks
- Need to: Load plugins and match auth handlers to URLs

**Questions:**
- How do we match URLs to auth handlers? By domain? By channel name?
- Do we need a new plugin interface or use existing `conda_auth_handler`?
- Should auth resolution be synchronous or async-capable?

**Decision Needed:** Auth integration architecture?

**Recommendation:**
1. Reuse existing `conda_auth_handler` hook
2. Match by URL prefix (e.g., "https://anaconda.org/conda" → auth handler)
3. Keep synchronous for Phase 1a (async in Phase 1b if needed)

---

### Q6: Testing & Mocking Strategy

**Question:** How should we mock HTTP responses in tests?

**Context:**
- Current code probably uses `pytest-vcr`, `responses`, or similar
- We need to test all Fetch implementations (requests, httpx, curl) with same mocks
- Should mocks be part of FetchResponse protocol or separate?

**Questions:**
- Do we use `httpbin.org` for integration tests?
- Do we use `pytest.fixture` for mock responses?
- Should we mock at the Fetch level or HTTP library level?

**Decision Needed:** Test infrastructure approach?

**Recommendation:**
- Use `pytest` fixtures with `httpbin` for integration tests
- Create mock FetchResponse objects for unit tests (simple dataclass)
- Test each implementation against the same test suite (parametrized pytest)

---

## Medium-Priority Questions

### Q7: Streaming Response Handling

**Question:** How should we handle partial/incomplete responses?

**Context:**
- RequestsResponse wraps requests.Response which handles streaming internally
- What if iter_bytes() is called but connection drops?
- Should we have automatic retry logic?

**Decision Needed:** Error handling for partial downloads?

**Recommendation:** Keep it simple for Phase 1a:
- Raise FetchConnectionError if stream is interrupted
- Add retry logic in Phase 1b if needed
- Document that client is responsible for retry logic (e.g., with tenacity)

---

### Q8: Progress Callback Design

**Question:** What should progress_callback signature be?

**Current:** `Callable[[int, int], None]` → (downloaded_bytes, total_bytes)

**Issues:**
- If total_bytes is unknown (chunked encoding), what do we pass?
- Should we pass FetchProgressEvent instead of raw numbers?
- Should progress_callback be part of FetchRequest or separate?

**Decision Needed:** Progress callback API?

**Recommendation:** Keep current simple design:
- Pass (downloaded, total) where total can be 0 if unknown
- Caller is responsible for handling unknown totals
- Add FetchProgressEvent in Phase 1b if multiplexing needs it

---

### Q9: Headers Handling

**Question:** Should header keys be case-sensitive or case-insensitive?

**Context:**
- HTTP headers are case-insensitive per spec
- Python dicts are case-sensitive
- requests.Response.headers is case-insensitive

**Options:**
1. Return `requests.structures.CaseInsensitiveDict` (preserve requests behavior)
2. Return `dict` (simple, but case-sensitive)
3. Return custom CaseInsensitiveDict (control behavior)

**Decision Needed:** Header dict type?

**Recommendation:** Return plain `dict` for Phase 1a (simpler). If case-insensitivity
matters, wrap in CaseInsensitiveDict in Phase 1b.

---

### Q10: JSON Response Parsing

**Question:** Should FetchResponse.json() handle different content-types?

**Current:** Delegates to requests.Response.json() which uses chardet for encoding

**Questions:**
- Should we support "application/json" AND "text/json" AND "application/ld+json"?
- Should we auto-detect encoding like requests does?
- What if response is not JSON but claims to be?

**Decision Needed:** JSON parsing behavior?

**Recommendation:** Keep simple for Phase 1a:
- Delegate to library (requests.Response.json())
- Only support standard "application/json"
- Let library handle encoding detection

---

### Q11: SSL/Certificate Handling

**Question:** How should client certificates and CA bundles be handled?

**Context:**
- FetchRequest has `verify` (SSL verification) and `cert` (client cert)
- Should these be strings (file paths) or objects?
- Different libraries handle these differently

**Decision Needed:** Certificate API design?

**Recommendation:** Keep as strings (file paths) for Phase 1a:
- `verify=True/False` or `verify="/path/to/ca-bundle.crt"`
- `cert="/path/to/cert.pem"` or `cert=("/path/to/cert.pem", "/path/to/key.pem")`
- Implementations convert to library-specific formats

---

### Q12: Timeout Handling

**Question:** How should timeouts be specified?

**Current:** `timeout: tuple[float, float] | None` → (connect_timeout, read_timeout)

**Issues:**
- Only handles connect + read, what about total timeout?
- Some libraries use different tuple formats
- Should timeout be per-request or per-fetch instance?

**Decision Needed:** Timeout API?

**Recommendation:** Current design is good:
- (connect_timeout, read_timeout) tuple
- None means no timeout
- Add total_timeout in Phase 1b if needed

---

## Low-Priority Questions (Can be deferred)

### Q13: Async Support

**Question:** Should Fetch protocol have async variants?

**Answer for Phase 1a:** No - keep synchronous only.
Async variants can be added in Phase 1b+ as separate AsyncFetch protocol.

### Q14: Connection Pooling

**Question:** Should Fetch instances be reusable/poolable?

**Answer for Phase 1a:** Yes - get_fetch_cached() enables this.
Keep session alive across requests for connection reuse.

### Q15: Multiplexing API

**Question:** What should FetchResponseEvent types look like?

**Answer for Phase 1a:** Defer - not needed until Phase 1c (CurlFetch).
Use Union types when implementing.

---

## Implementation Checklist

### Before Starting Code
- [ ] Resolve Q1 (Error handling approach)
- [ ] Resolve Q2 (FetchRequest type)
- [ ] Resolve Q3 (download.py refactoring scope)
- [ ] Resolve Q4 (Direct download adapters)
- [ ] Resolve Q5 (Auth integration)
- [ ] Resolve Q6 (Testing strategy)

### Before Phase 1a Release
- [ ] Implement Q7 (Streaming errors)
- [ ] Implement Q8 (Progress callbacks)
- [ ] Implement Q9 (Headers handling)
- [ ] Implement Q10 (JSON parsing)
- [ ] Implement Q11 (SSL/certs)
- [ ] Implement Q12 (Timeouts)

### For Phase 1b+
- [ ] Q13 (Async support)
- [ ] Q14 (Connection pooling)
- [ ] Q15 (Multiplexing API)

---

## Decision Log

Document decisions as they're made:

| Date | Question | Decision | Rationale |
|------|----------|----------|-----------|
| YYYY-MM-DD | Q1 | Wrapper approach | Keep exception types familiar to users |
| YYYY-MM-DD | Q2 | Keep dataclass | Simpler for implementations |
| YYYY-MM-DD | Q3 | Minimal refactor | Get Phase 1a working quickly |
| | | | |

---

## Next Steps

1. Review this document and answer each question
2. Update Decision Log with choices
3. Record decisions in design docs (PLUGGABLE_REQUESTS_IMPLEMENTATION_PLAN.md)
4. Start Phase 1a implementation

**Timeline:** Expected decision review: May 7-8, 2026
**Implementation start:** May 9, 2026 (after decisions made)
