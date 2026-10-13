# ADR-0019: A tag for each tenant's workspace

**Status:** Accepted
**Date:** 2026-10-13
**Deciders:** Alex Nodeland

## Context

artifactr's and reflexr's LiteLLM gateways tag every model request with `tenant:<id>` and `workspace:<id>`, and LiteLLM adds up each tag's spend by day. A workspace id is chosen by its tenant's callers, so two tenants can have a workspace of the same id, and LiteLLM's total for `workspace:<id>` is theirs together. portalr's admin Usage page needs each tenant's spend by workspace, which neither tag gives.

LiteLLM stores a tag as text of any length and character, and checks neither. Its tag queries, such as `/tag/daily/activity?tags=`, take a comma-separated list. Tenant and workspace ids are plain strings in the libraries: they may hold a `/`, a comma, or anything else.

## Decision

- **Every model request through either gateway carries a third tag, `tenant-workspace:<tenant>/<workspace>`,** beside the `tenant:` and `workspace:` tags, which stay as they are.
- **Each id in it is percent-encoded:** every character but ASCII letters, digits and `-._~`, as `urllib.parse.quote(id, safe="")` does, in UTF-8. So the one `/` in the tag is the separator, no comma can split it in a tag query, and a reader decodes the two ids exactly. `acme` and `launch` give `tenant-workspace:acme/launch`; `acme/eu` and `q3,plan` give `tenant-workspace:acme%2Feu/q3%2Cplan`.
- **No id is shortened,** since LiteLLM sets no limit, and a shortened id could make two workspaces one.
- **`lattice_core.litellm.request_tags(tenant_id, workspace_id)` builds the three tags,** and both gateways use it, so the format is one code path. It is a contract with portalr, which reads the tag.

## Options considered

| Option | For | Against |
|---|---|---|
| **A third tag, each id percent-encoded (chosen)** | Unambiguous whatever the ids hold; one query per tenant's workspace | Ids are read encoded in LiteLLM's own UI |
| `tenant-workspace:<tenant>/<workspace>` unencoded | Readable | A `/` in an id makes it ambiguous, and a comma splits the tag in a query |
| Make `workspace:` carry the tenant | One tag fewer | Changes the meaning of a tag dashboards and budgets may already use |
| Read spend by team key instead | No new tag | A tenant's team key spans all its workspaces |

## Consequences

- Easier: portalr reads a tenant's spend by workspace from LiteLLM's daily tag totals.
- Harder: LiteLLM keeps one more tag per request, and so one more daily row per tenant's workspace.
- Harder: changing the format later changes the contract with portalr; a reader of old days must still read this one.
