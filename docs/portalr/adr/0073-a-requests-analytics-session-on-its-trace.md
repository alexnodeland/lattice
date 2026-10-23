# ADR-0073: A request's analytics session, on its trace

**Status:** Accepted
**Date:** 2026-10-23
**Deciders:** Alex Nodeland

Implements "traces both ways" in phase 5 of [lattice RFC-0008](../../rfcs/0008-portalr-product-analytics.md) (portalr product analytics, [#361](https://github.com/alexnodeland/lattice/issues/361)). It follows [ADR-0071](0071-adoption-the-tenants-read-and-page.md), the tenant's adoption.

## Context

- **A person's events are under a session portalr's relay signs for them:** `nonce.signature`, where the nonce is when it began and 16 random hex digits, and the signature is the deployment's key over the person and the nonce. The events hold no trace id.
- **portalr has no tracing of its own.** The application's server spans come from lattice-core's instrumentation of FastAPI, and the spans that name a tenant (`tenant.id`) come from the libraries, artifactr's and reflexr's. The requests worth linking are the libraries', such as sending a message, not portalr's.
- **`session.id` on a span already means an artifactr thread,** which Traces searches by and the trace view links to.

## Decision

- **The browser carries the session.** While a person shares how they use the app, the capture add-on hands the signed session to the client, and every REST request carries it in `X-Portalr-Analytics-Session`. Saying no clears it, and so does a session that couldn't be signed.
- **`SessionStamp`, an ASGI middleware of portalr's,** reads the header and sets `portalr.analytics.session = <nonce>` on the request's server span, but only where all of these hold:
  - the header is there: without it, nothing more is done;
  - the application's own resolver, the one portalr's router takes, says the caller is a person, not a key's principal. It is asked only then. It reads the token or key and writes nothing, and nothing is kept between requests;
  - `Relay.session_of` finds the value is that person's own session, signed by portalr and fresh;
  - the person still says yes.

  Anything else is no stamp, and is never logged: a forged, expired, bare, overlong or non-ASCII value, another person's session, or a resolver or consent that fails. The request goes on as it came, whatever the stamp does.
- **The template installs it** in `Portal.mount`, where the relay is made, so only with the portal and analytics configured. A variant without them is unchanged. The application's FastAPI instrumentation, added after, runs outside it, so the span it stamps is the request's server span, for every route: the libraries', portalr's and the application's own. The template's test checks this with an in-memory exporter.
- **Traces of a session:** `GET /portalr/v1/traces` takes `analytics_session`, so it needs no endpoint of its own.
  - It is checked against the relay's shape (`^\d{1,12}-[0-9a-f]{16}$`), and the window is at most 91 days.
  - Its TraceQL is the tenant's search and the session's, each quoted: `{ span.tenant.id = "<tenant>" … } && { span.portalr.analytics.session = "<nonce>" }`. A trace is found only where it holds both one of the tenant's spans and the session's server span.
- **The trace view shows "Analytics session"** where a span carries it. The field links to Traces filtered by that session over the last 7 days.
- **Who sees the nonce:** those who may read the tenant's telemetry (`portalr:read_telemetry`, its owners and admins), in the trace view, as `session.id` and `user.id` already are; and operators, in Tempo and Grafana. The attribute is on `SAFE_ATTRIBUTES` only for the trace view, which nothing else derives from. The nonce is pseudonymous: random, of no one, and not the person's id or their keyed hash. Only their analytics events share it.

## Options considered

- **`session.id`:** it already means a thread, so the two would collide.
- **Stamping in portalr's router:** only portalr's own requests would be marked, which are consent and relay calls, not what people do.
- **A W3C `baggage` entry from the browser:** the value would be the browser's word, never checked.
- **An endpoint for a session's traces:** the filter on `/v1/traces` has the same isolation, with less to keep.

## Consequences

- A tenant's admins go from a trace to every request of the same analytics session.
- **Sizes:** the analytics add-on is 594 of its 600 bytes, and the app total 473,311 of 475,000, about 90 bytes more than before.
- The browser sends the header only while the person says yes, and the server stamps only what it can check, so a person who said no has no session on any trace.
