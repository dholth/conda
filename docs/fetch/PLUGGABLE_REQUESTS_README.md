# Pluggable Requests Implementation Plan - Documentation Overview

This directory contains comprehensive planning documentation for implementing a pluggable HTTP fetch system in conda, enabling support for alternative HTTP libraries (httpx, curl, etc.) beyond the current requests-only architecture.

## Quick Links

- **[PLUGGABLE_REQUESTS.md](./PLUGGABLE_REQUESTS.md)** — Original specification and problem statement
- **[PLUGGABLE_REQUESTS_IMPLEMENTATION_PLAN.md](./PLUGGABLE_REQUESTS_IMPLEMENTATION_PLAN.md)** — Comprehensive implementation plan (10 phases)
- **[PLUGGABLE_REQUESTS_ARCHITECTURE.md](./PLUGGABLE_REQUESTS_ARCHITECTURE.md)** — Architecture diagrams and system design
- **[PLUGGABLE_REQUESTS_QUICK_START.md](./PLUGGABLE_REQUESTS_QUICK_START.md)** — Developer checklist and quick start guide

## Document Guide

### 1. Original Spec: PLUGGABLE_REQUESTS.md

**Purpose:** Problem statement and motivation

**Contains:**
- Why requests-only architecture causes performance problems
- HTTP/1.1 vs HTTP/2 comparison
- Reference to unearth's design pattern
- Problem with auth handling
- Fallback strategy

**When to read:** First, to understand the business case

---

### 2. Implementation Plan: PLUGGABLE_REQUESTS_IMPLEMENTATION_PLAN.md

**Purpose:** Complete step-by-step implementation roadmap

**10 Sections:**
1. **Executive Summary** — Goals and scope
2. **Current State Analysis** — Existing architecture analysis
3. **Architecture & Design** — Core abstractions (Fetch, FetchResponse, AuthHandler protocols)
4. **Module Structure** — File layout and organization
5. **Implementation Details** — Code-level design for each component
6. **Testing Strategy** — Test organization and coverage targets
7. **Backward Compatibility & Deprecation** — Timeline and migration path
8. **Plugin System Integration** — How pluggable fetches work
9. **Documentation Plan** — User and developer docs needed
10. **Implementation Timeline** — Weekly breakdown
11. **Success Criteria** — Functional and non-functional requirements
12. **Risk Assessment** — Known risks and mitigations
13. **Appendices** — Examples and reference materials

**When to read:** After understanding the problem, before starting implementation

**Best for:**
- Getting high-level overview of the system
- Understanding design decisions
- Planning the work
- Risk analysis

---

### 3. Architecture Document: PLUGGABLE_REQUESTS_ARCHITECTURE.md

**Purpose:** Visual and detailed technical architecture

**Contains:**
- ASCII system architecture diagram
- Data flow diagrams for single and multiplexed downloads
- Session vs. Fetch migration pattern
- Error handling exception hierarchy
- Module import tree
- Configuration options
- Feature comparison matrix (Requests vs. Httpx vs. Curl)
- Plugin extension points
- Testing strategy overview
- Rollout schedule

**When to read:** When you need visual understanding or detailed technical reference

**Best for:**
- Understanding data flow
- Exception mapping
- Plugin integration points
- Configuration
- Architecture review

---

### 4. Quick Start Guide: PLUGGABLE_REQUESTS_QUICK_START.md

**Purpose:** Actionable developer checklist for Phase 1a (RequestsFetch)

**Contains:**
- Step-by-step checklist (13 steps)
- Code templates and examples
- Phase 1b overview (httpx, curl)
- Testing template
- Common issues & troubleshooting
- Success metrics

**When to read:** When ready to start coding

**Best for:**
- Developers implementing Phase 1a
- Step-by-step guidance
- Code templates
- Quick reference
- Debugging

---

## Reading Recommendations

### For Different Roles

**Project Manager / Tech Lead:**
1. PLUGGABLE_REQUESTS.md (5 min) — Understand motivation
2. PLUGGABLE_REQUESTS_IMPLEMENTATION_PLAN.md Sections 0-1 (10 min) — Current state & scope
3. PLUGGABLE_REQUESTS_IMPLEMENTATION_PLAN.md Section 10 (5 min) — Timeline & success criteria

**Architect / Tech Reviewer:**
1. PLUGGABLE_REQUESTS.md (5 min) — Motivation
2. PLUGGABLE_REQUESTS_IMPLEMENTATION_PLAN.md Sections 2-3 (20 min) — Architecture & design
3. PLUGGABLE_REQUESTS_ARCHITECTURE.md (15 min) — Diagrams & details
4. PLUGGABLE_REQUESTS_IMPLEMENTATION_PLAN.md Section 7 (5 min) — Backward compat

**Developer (Phase 1a):**
1. PLUGGABLE_REQUESTS.md (5 min) — Motivation
2. PLUGGABLE_REQUESTS_ARCHITECTURE.md (10 min) — Architecture overview
3. PLUGGABLE_REQUESTS_QUICK_START.md (20 min) — Follow checklist
4. PLUGGABLE_REQUESTS_IMPLEMENTATION_PLAN.md Section 5 (as needed) — Deep dive

**Plugin Developer (Future Httpx/Curl):**
1. PLUGGABLE_REQUESTS.md (5 min) — Motivation
2. PLUGGABLE_REQUESTS_ARCHITECTURE.md "Plugin Extension Points" (5 min) — Integration
3. PLUGGABLE_REQUESTS_IMPLEMENTATION_PLAN.md Appendix A (10 min) — Examples
4. PLUGGABLE_REQUESTS_QUICK_START.md Section "Phase 1b" (5 min) — Template

---

## Key Concepts

### Fetch Protocol

The core abstraction: a `typing.Protocol` (duck typing) that allows any HTTP library (requests, httpx, curl) to be used interchangeably.

```python
class Fetch(Protocol):
    def get(self, url: str, **kwargs) -> FetchResponse: ...
    def head(self, url: str, **kwargs) -> FetchResponse: ...
    def get_file(self, url, fileobj, progress_callback=None) -> None: ...
```

### RequestsFetch

Adapter wrapping the existing `requests.Session` to implement the Fetch protocol. Provides zero-overhead backward compatibility.

### Exception Hierarchy

Unified exception mapping from any HTTP library (requests, httpx, curl) to a standard set of fetch exceptions, then to conda exceptions.

```
requests.HTTPError → FetchHTTPError → CondaHTTPError
requests.Timeout → FetchTimeout → (no conda mapping yet)
requests.SSLError → FetchSSLError → CondaSSLError
```

### Auth Integration

Extends existing conda plugin system to work with any HTTP library. `ChannelAuthResolver` maps URLs to auth handlers transparently.

### Multiplexing (Future)

`FetchMultiplexer` protocol enables concurrent requests without blocking. Useful for downloading many small files (e.g., shards). Implemented by curl and httpx; requests falls back to serial.

---

## Implementation Phases

### Phase 1a: RequestsFetch (CURRENT FOCUS)
- Build core fetch abstraction
- Wrap requests with RequestsFetch
- Update download.py to use new interface
- Full backward compatibility

**Timeline:** 2-3 weeks
**Effort:** 1 developer

### Phase 1b: HttpxFetch (FUTURE)
- Implement Fetch protocol using httpx
- HTTP/2 support
- Separate package: `conda-httpx`

**Timeline:** 1-2 weeks (after Phase 1a stable)
**Effort:** 1 developer

### Phase 1c: CurlFetch (FUTURE)
- Implement Fetch protocol + FetchMultiplexer using pycurl
- True multiplexing
- Separate package: `conda-curl`

**Timeline:** 2-3 weeks (after Phase 1a stable)
**Effort:** 1-2 developers

### Phase 2: Stabilization (FUTURE)
- Performance benchmarking
- Production testing
- Community feedback
- Production release

**Timeline:** 1-2 months
**Effort:** Shared across team

---

## Backward Compatibility

✓ **No breaking changes** — Existing code continues to work
✓ **Transparent migration** — Can swap fetches via env var: `CONDA_FETCH=httpx`
✓ **Gradual rollout** — Requests stays default for ≥2 releases
✓ **Deprecation path** — Clear timeline if removal is desired (currently not)

---

## Module Structure

```
conda/gateways/fetch/                      [NEW]
├── __init__.py                             Public API exports
├── types.py                                Fetch, FetchResponse protocols
├── request.py                              FetchRequest, exception hierarchy
├── response.py                             Response building, error mapping
├── auth.py                                 AuthHandler, ChannelAuthResolver
├── registry.py                             Fetch discovery & registration
└── implementations/
    ├── requests.py                         RequestsFetch adapter
    ├── httpx.py                            [FUTURE] HttpxFetch
    └── curl.py                             [FUTURE] CurlFetch

conda/gateways/connection/                 [MODIFIED - backward compat]
├── download.py                             Use fetch interface (internal only)
├── session.py                              Thin wrapper or unchanged
└── ... (rest unchanged)
```

---

## File Sizes & Complexity

| File | LOC | Complexity | Depends On |
|------|-----|-----------|-----------|}
| types.py | 150-200 | Low | None |
| request.py | 100-150 | Low | None |
| response.py | 200-300 | Medium | types, request |
| auth.py | 150-250 | Medium | types, request, plugins |
| registry.py | 100-150 | Medium | All above |
| implementations/requests.py | 150-250 | Medium | All above |
| tests (total) | 1000+ | Medium | Pytest, httpbin |

**Total new code:** ~1,200-1,500 lines (well-scoped, modular)

---

## Testing Coverage

### Unit Tests (tests/gateways/fetch/)
- Protocol compliance
- RequestsFetch implementation
- Auth handling
- Exception mapping
- Registry

**Target: >90% coverage**

### Integration Tests (tests/gateways/test_connection.py)
- Download with progress
- Error handling
- Auth flows
- Proxy support
- Backward compatibility with Session

**Coverage: All existing tests should pass unchanged**

---

## Success Metrics

After Phase 1a completion, you should observe:

✓ All tests pass (existing + new)
✓ Zero performance regression vs. current requests
✓ Can instantiate custom Fetch and register it
✓ Can swap fetches via `CONDA_FETCH` env var
✓ All conda download functionality works identically
✓ Code review approved
✓ CI/CD green

---

## Key Decision Points

**Decision 1: Protocol vs. ABC**
- ✓ Choose Protocol (duck typing, flexible, no base class coupling)
- Alternative: ABC (too rigid, breaks binary compatibility)

**Decision 2: Keep requests as default**
- ✓ Yes (no breaking changes, gradual adoption)
- Alternative: Deprecate requests immediately (too disruptive)

**Decision 3: Single registry or plugin hooks**
- ✓ Both (registry for discovery, plugins for registration)
- Alternative: Only env vars (not extensible)

**Decision 4: Sync or async**
- ✓ Sync (matches requests, easier migration)
- Async available via separate implementations (httpx, curl can be async)

---

## Known Limitations & Future Work

**Phase 1a:**
- No async support (added in httpx implementation)
- No multiplexing (added in curl implementation)
- Serial downloads only (same as current requests)

**Future phases:**
- Add async variants of Fetch for httpx
- Add FetchMultiplexer for curl, httpx
- Consider HTTP/3 support via httpx

---

## Getting Help

1. **Understanding the design?** → Read PLUGGABLE_REQUESTS_ARCHITECTURE.md
2. **Ready to code?** → Follow PLUGGABLE_REQUESTS_QUICK_START.md
3. **Need more detail?** → See PLUGGABLE_REQUESTS_IMPLEMENTATION_PLAN.md
4. **Original motivation?** → Read PLUGGABLE_REQUESTS.md

---

## Related Documents & Resources

- **unearth (reference):** https://github.com/pypa/unearth
- **conda-httpx (example):** https://github.com/dholth/conda-httpx
- **Conda deprecation policy (CEP 9):** https://conda.org/learn/ceps/cep-0009/
- **Conda release policy (CEP 8):** https://conda.org/learn/ceps/cep-0008/
- **Python typing.Protocol:** https://typing.python.org/en/latest/spec/protocol.html

---

## Document Maintenance

These documents should be updated when:
- Design decisions are revisited or changed
- Timeline shifts significantly
- New phases are added or modified
- Lessons learned from Phase 1a guide Phase 1b

Last updated: 2026-05-07

---

End of README
