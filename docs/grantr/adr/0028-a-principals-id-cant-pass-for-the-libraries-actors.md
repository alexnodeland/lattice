# ADR-0028: A principal's id can't pass for the libraries' actors

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

A key's service principal reaches artifactr as an external agent whose `client_id` is the principal's id. relayr's code rules act in artifactr as external agents too, `reflexr:<rule>`, and stackr's template checks those as the application, by their `client_id` ([ADR-0025](0025-the-application-lists-tenants-and-workspaces-and-writes-for-code-rules.md)). A service principal's id was any string, so a tenant's admin could make one named `reflexr:<a code rule>`, issue it a key, and act in artifactr as the application. This is a security fix.

The template can't tell how an artifactr actor was made: it holds no record of whether a key or relayr made it. Its id has to be enough.

## Decision

- **A service principal's id holds no `:`, `~` or whitespace, and isn't empty** (`PrincipalId`). The libraries' own actors' ids hold a `:` (relayr's are `reflexr:<rule>`), and `~` is grantr storage's, so the two kinds of id can't meet. An invalid id is refused wherever a principal is made: in `Grants`, and as 422 in the admin API, for a new member, a key, and removing a member. The application's own principal's id must be one too.
- **The template takes a rule's actor as the rule only when it acts for no one,** as relayr's `is_rule_actor` now says: a code rule's as the application, a stored rule's as the rule in its workspace. A person's client, whatever its id, is checked as the person, and any other client whose id no principal can take holds nothing, rather than failing the check.

## Options considered

| Option | For | Against |
|---|---|---|
| **Keep principals' ids out of the libraries' namespace (chosen)** | One rule in grantr, checked wherever a principal is made | Ids narrow; it lands before grantr's first release, so no stored id is affected |
| Record in the actor how it was made | The template would ask how, not what it is called | A field in artifactr's actors that every surface must set, and trust |
| Refuse only `reflexr:` | The narrowest change | The next library's prefix opens the same hole |

## Consequences

- Easier: no key, now or later, can take an id the libraries' own actors use.
- Harder: nothing, for stored data: the narrowing lands before grantr's first release, so no deployment holds such an id.
