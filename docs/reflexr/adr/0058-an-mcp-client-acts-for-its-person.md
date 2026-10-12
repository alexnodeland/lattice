# ADR-0058: An MCP client acts for its person

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Follows [ADR-0056](0056-access-asked-in-every-workspace-method.md), and [lattice RFC-0001](../../rfcs/0001-grantr-identity-and-access.md)'s subject table.

## Context

An application's `authorize` hook decides who an actor is. A person can connect an MCP client with their own token, and a client can connect with credentials of its own, such as a service principal's key. reflexr's `ExternalAgentActor` said only which client acted, so a hook couldn't tell a person's client from a client acting for no one, and artifactr's actor, which says whom a client acts for, had no twin in reflexr.

## Decision

- **`ExternalAgentActor` gains `on_behalf_of: UserActor | None`,** as artifactr's has: the person the client acts for, if it acts for one. An application's MCP resolver sets it when a person connects with their own token, and an `authorize` hook checks such a client as that person.
- **Nothing else changes:** the client is still the participant, so attribution and de-duplication are as before, and a client with credentials of its own leaves it unset.

## Options considered

| Option | For | Against |
|---|---|---|
| **`on_behalf_of` on the actor (chosen)** | The same shape as artifactr's, so one application maps both libraries' actors alike | Every actor's JSON has one more field |
| A naming convention for `client_id` | No change to the model | A hook would parse ids, and a person's id could collide with a client's |

## Consequences

- Easier: a person's MCP client is checked as them in both libraries.
- Harder: the protocol's schema changes, with a field that defaults to none.
