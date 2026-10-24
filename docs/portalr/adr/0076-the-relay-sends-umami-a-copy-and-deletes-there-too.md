# ADR-0076: The relay sends Umami a copy, and deletes there too

**Status:** Accepted
**Date:** 2026-10-23
**Deciders:** Alex Nodeland

portalr's side of [stackr ADR-0050](../../stackr/adr/0050-umami-a-profile-for-operators-journeys-on-the-postgres-adapter.md), for [lattice RFC-0008](../../rfcs/0008-portalr-product-analytics.md) ([#361](https://github.com/alexnodeland/lattice/issues/361)).

## Context

- **ClickHouse is the record** of a person's events, and they are deleted from it when the person says no.
- **Umami keeps journeys by session.** Each session is derived from its website, the client's address and agent, and a distinct id it is given.

## Decision

- **The relay sends Umami a copy of what it kept:** only after the write to ClickHouse, and only once the person's yes has been read again.
  - Each event goes to `/api/send` from portalr's own address, with the fixed user agent `portalr-relay`. No person's address, `X-Forwarded-For` or user agent is sent.
  - The route and the registry's props go as the event's URL and data. Nothing else goes, and nothing a person wrote.
  - **The copy is never waited on.** It is sent in the background, so the relay's answer, and what it recorded, are the same whether Umami is up, down or answering nonsense.
  - Any failure of Umami's, of whatever kind, is caught at its client, logged by its type, and dropped: Umami is never the record. After one, the copies rest for 30 seconds, sending nothing, and each request to Umami waits at most 2 seconds.
  - **A no that lands while the copy is sent** is read again after it. If the yes is gone, a deletion is owed and tried at once, so no session is left in Umami, as a batch written while a no lands is deleted in ClickHouse.
- **A person in Umami is `<tenant>:<keyed hash>`,** Umami's distinct id. So each person has a session of their own in each tenant, and never their id.
- **Deleting reaches Umami.**
  - Saying no deletes the person's sessions there, with their events, in every tenant. portalr's Umami user, who owns the website, signs in, searches for the hash (every page of the answer), reads each session to check its distinct id is the person's exactly, and deletes it.
  - It searches again until a round finds none of theirs. A deletion that still finds some after 10 rounds isn't done, and stays owed.
  - The deletion owed in ClickHouse stays owed until both are done, so an outage in either is retried.
  - The removal from one tenant, in ADR-0075 (#695), deletes that tenant's session alone, once that change is on main.
- **Operators' Tools page** gets a link to the website in Umami, with a tenant's other links, recorded as they are. It shows every tenant's journeys, since Umami has none.
- **The template** reads `PORTAL_UMAMI_URL`, `PORTAL_UMAMI_WEBSITE_ID`, `PORTAL_UMAMI_PASSWORD` and `PORTAL_UMAMI_UI_URL`. Without the first three, nothing goes to Umami.

## Options considered

- **Umami's own tracker in the browser:** the browser would send Umami its address and agent, and Umami's ingest would face the internet.
- **A website per tenant:** it needs a tenant's website made on demand, with an admin's rights in portalr. The tenant in the distinct id keeps one website, and lets a tenant's sessions be found.

## Consequences

- Umami holds a person's journeys, by tenant, as pseudonymous ids, until the person says no or Umami's own retention ends.
- A person's "no" now needs ClickHouse and Umami both to answer before it is settled.
