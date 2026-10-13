# ADR-0019: A tag for each tenant's workspace

**Status:** Accepted
**Date:** 2026-10-13
**Deciders:** Alex Nodeland

## Context

artifactr's and reflexr's LiteLLM gateways tag every model request with `tenant:<id>` and `workspace:<id>`, and LiteLLM adds up each tag's spend by day. A workspace id is chosen by its tenant's callers, so two tenants can have a workspace of the same id, and LiteLLM's total for `workspace:<id>` is theirs together. portalr's admin Usage page needs each tenant's spend by workspace, which neither tag gives (portalr ADR-0028, in [#188](https://github.com/alexnodeland/lattice/pull/188)).

The proxy stackr runs, `ghcr.io/berriai/litellm-non_root` v1.103.0, stores a tag as text of any length and character, and checks neither. Its tag queries, such as `/tag/daily/activity?tags=` (`tag_management_endpoints.py:759`), take a comma-separated list, and keep `%` as it is. Tenant and workspace ids are plain strings in the libraries: they may hold a `/`, a comma, a `%`, or anything else.

## Decision

- **Every model request through either gateway carries a third tag, `tenant-workspace:<tenant>/<workspace>`,** beside the `tenant:` and `workspace:` tags, which stay as they are.
- **Each id in it is percent-encoded:** in UTF-8, every byte but those of RFC 3986's unreserved characters (ASCII letters, digits and `-._~`) as `%XX`, in uppercase hex. That is Python's `urllib.parse.quote(id, safe="")`. JavaScript's `encodeURIComponent` differs: it leaves `!'()*` as they are, so a JavaScript writer must encode those too. The one `/` in the tag is the separator, and no comma can split it in a tag query.
- **The reading rule:** strip the `tenant-workspace:` prefix, split at the first `/`, and percent-decode each half as UTF-8. Anything else is no workspace tag. For example:
  - `acme` and `launch` give `tenant-workspace:acme/launch`;
  - `acme/eu` and `q3,plan` give `tenant-workspace:acme%2Feu/q3%2Cplan`;
  - `100%` and `a%2Fb` give `tenant-workspace:100%25/a%252Fb`.
- **A query names the tag encoded again,** as any query parameter is (an HTTP client's `params` does it), since the tag holds `%` and `/`.
- **No id is shortened,** since LiteLLM sets no limit, and a shortened id could make two workspaces one.
- **`lattice_core.tags` is the format's one implementation.** It is in lattice-core without an extra, as stdlib code:
  - `workspace_tag` writes the tag;
  - `parse_workspace_tag` reads it back;
  - `request_tags` gives a request's three tags.
  - Both gateways use `request_tags`, and portalr reads with `parse_workspace_tag`, depending on lattice-core-ai with no extra.

## Options considered

| Option | For | Against |
|---|---|---|
| **A third tag, each id percent-encoded (chosen)** | Unambiguous whatever the ids hold; one query per tenant's workspace | Ids read encoded in LiteLLM's own UI |
| `tenant-workspace:<tenant>/<workspace>` unencoded | Readable | A `/` in an id makes it ambiguous, and a comma splits the tag in a query |
| Make `workspace:` carry the tenant | One tag fewer | Changes the meaning of a tag that dashboards and budgets may already use |
| Read spend by team key instead | No new tag | A tenant's team key spans all its workspaces |

## Consequences

- Easier: portalr reads a tenant's spend by workspace from LiteLLM's daily tag totals.
- Harder: requests made before this change carry no `tenant-workspace:` tag, so their spend has no split by workspace.
- Harder: LiteLLM keeps one more tag per request, and so one more daily row per tenant's workspace.
- Harder: changing the format later changes the contract with portalr; a reader of old days must still read this one.
