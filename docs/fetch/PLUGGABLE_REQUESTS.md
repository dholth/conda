# Making `requests` a plugin in conda

`conda`'s network interface is welded to requests. This causes performance
problems because `requests` is not able to use the [11-year-old HTTP/2
protocol](https://en.wikipedia.org/wiki/HTTP/2).

There is delay between a request and response. With the current HTTP/1.1
protocol that delay happens serially per TCP connection to a remote server; but
with HTTP/2, many requests can fire in parallel on the same connection. This
reduces connection setup overhead and latency.

Even with HTTP/2 it could still be valuable to have more than one TCP
connection, since every transfer multiplexed over a single TCP stream slows down
when packets are dropped. We can
probably saturate our bandwidth with just a few parallel package downloads, but
it helps to have a new request fire while the previous request is still ongoing.[^1]

[^1]: As observed when we added parallel downloads to conda.

HTTP/1
```
[TCP, ssl][request] lag [transfer][request] lag [transfer]
```

HTTP/2
```
[TCP, ssl][request 1] latency [transfer transfer transfer]
            [request 2] latency [transfer transfer transfer]
                                    [request 3] latency [transfer]...
```

> In this simple diagram request 1 and 2 are both waiting at the same time.
> Request 3's latency overlaps with other transfers, avoiding an idle period,
> making better use of available bandwidth.

The clearest win for HTTP/2 is with shards, where the request latency can easily
dominate as we are fetching many small objects.

## What conda does today

When we need to make parallel requests, conda opens a `ThreadPoolExecutor` [on the spot](https://github.com/conda/conda/blob/53c1530a359a686fe2f80eeda5135a730855d08e/conda/core/package_cache_data.py#L840). Its concurrency strategy is not centralized.

## Unearth shows the way

In `unearth`, the authors found the common API surface between `requests` and
`httpx`, expressed with
[`typing.Protocol`](https://typing.python.org/en/latest/spec/protocol.html).
Instead of asking for `def fetch_package(s: requests.Session)`, unearth asks for
the `Fetcher` protocol. If unearth tries to use something that's only available
on `Session`, the type checker warns.

## The missing API

What's missing from `Requests`, but [present in `curl`](https://everything.curl.dev/transfers/drive/multi.html), is an API to
run multiple transfers at once. `conda` needs this to decouple itself from the networking library's concurrency model.

In [conda-libmamba-solver's shard code](https://github.com/conda/conda-libmamba-solver/blob/main/conda_libmamba_solver/shards_subset.py#L622) we handle this
with a thread that accepts URLs from the main thread; fetches them; and enqueues
responses back to the main thread. It can accept new requests at any time (we
don't have to wait for a batch of requests to finish before adding another) and
responses are objects specific to sharded repodata. We have an alternate network
worker for "offline" mode that always fails; and an experimental `http/2`
worker. The main thread isn't aware of the concurrency model or http library
used.

A general plugin might accept `Request` objects in an input queue; send many
notification objects back on the output queue for progress bars; and would need
a function to map <insert library here> exceptions to a shared set of `conda`
networking exceptions.

## Adapting auth handling to other libraries

`conda` [has a few existing plugins](https://github.com/dholth/conda-httpx#conda-features-which-can-affect-request-headers) that affect HTTP. In
[conda-httpx](https://github.com/dholth/conda-httpx#conda-features-which-can-affect-request-headers) I've tried to adapt the requests auth handler to httpx, but
It's hard to write and verify a completely general adapter.

`httpx` [has a different auth API](https://www.python-httpx.org/advanced/authentication/) with sync and async variants, and a version that performs no I/O and works with either concurrency model. I remember thinking the httpx system was a little more adaptable than requests'.

For example `conda`'s [Request Headers](https://docs.conda.io/projects/conda/en/stable/dev-guide/plugins/request_headers.html#request-headers) plugin is independent of the http library. It would work if the http library plugin was mostly expected to set `Authorization: Bearer <secret>` tokens on a known set of URL prefixes.[^2]

[^2]: It would be nice but not critical to update dot-org from `Authorization: token <secret>` to `Bearer <secret>`

`Channel()` complicates things. It would be better if we could map auth per URL or
URL prefix, and not parse every URL with `Channel()` in the network layer. If the user is specifying auth per channel in configs, `conda` would need to expand it to URL -> auth before sending this information to the network layer.

Conda also basically expects us to use a different `Session()` per channel, [attaching auth to sessions](https://github.com/conda/conda/blob/main/conda/gateways/connection/session.py#L197-L200). This is broken now that a channel can reference other base_url serving packages from a different auth than repodata. This has always been broken because it should be valid to share a connection pool for all channels on repo.anaconda.com or conda.anaconda.org.

## Fallback to requests

Since the existing system is so "rich", the first release would give simple users (i.e. the unauthenticated
`conda-forge` user) faster networking while shunting "weird" requests (`s3://`, unknown
auth) to conda's current `Session()`.

## Or use niquests

A ludicrously feature-rich drop-in replacement for requests.

## Or use py-rattler for HTTP

rattler contains an http system that understands anaconda.org etc. auth.
