# RFC-0010: People outside the tenant: guests, share links, public forms and client portals

**Status:** Draft
**Author:** Alex Nodeland
**Created:** 2026-10-29
**Discussion:** the pull request that adds this file

## Summary

Today everyone who can see anything in lattice is a member of a tenant. This RFC adds four ways for people outside a tenant to take part, all built on grantr's one check:

- **Guests**: people invited to specific threads, artifacts or workspaces, not to the tenant. They hold a new tenant role, `guest`, which lists nothing, and their grants expire.
- **Share links**: one artifact, at its head or at one version, readable without an account through a new subject, the link.
- **Public forms**: forms that take submissions from people with no account, behind rate limits, a captcha and spam scoring.
- **Client portals**: a branded home for one outside party, listing what is shared with its guests.

Every kind is off by default, switched per tenant and per workspace, audited, and revocable from one admin page. Agents never share outside on their own: inviting a guest or making a link is a proposal that a person accepts.

Tracked by #1118.

## Motivation

Most teams work with people outside their organisation: contractors, clients, auditors, board members, applicants. lattice gives them no way in. grantr's model ([lattice RFC-0001](0001-grantr-identity-and-access.md)) stands on three rules:

- a user reaches a tenant only through a membership ([grantr ADR-0005](../grantr/adr/0005-a-users-tenants-from-grantrs-memberships.md)), and the resolver refuses everyone else;
- the tenant's `member` role holds `artifactr:read_workspaces`, the listing of every workspace the caller may open ([grantr ADR-0022](../grantr/adr/0022-a-tenants-members-list-its-workspaces.md));
- a new thread or artifact is visible to everyone with a role in its workspace ([grantr ADR-0003](../grantr/adr/0003-visible-to-the-workspace-unless-restricted.md)).

So the only way to let a client review one document is to make them a member, who can then list the tenant's workspaces, see other members by email ([portalr ADR-0038](../portalr/adr/0038-people-by-email.md)), and keep their access until someone remembers to remove them. Today people export a PDF instead, which loses live updates and the thread around the document, and copies data out with no record. A form, likewise, can only be submitted by someone with access to its thread ([lattice RFC-0005](0005-forms-dashboards-and-mini-apps.md)), so intake forms, surveys and sign-ups can't be run in lattice at all.

For many teams this decides whether they can adopt lattice. Why now: the compliance work (#1042) is designing data classes (#1044), retention (#1046), access reviews (#1051) and the tamper-evident audit log (#1049). Outside access is the riskiest thing those controls govern, so designing it now lets both fit together, rather than retrofitting either.

## Design

### Principles

1. **One check.** Guests, links and public submitters are subjects in grantr's model. Every read and command goes through the check it already makes, and the `hidden` and `resources` filters that follow it ([grantr ADR-0002](../grantr/adr/0002-grants-down-to-threads-and-artifacts.md), [ADR-0024](../grantr/adr/0024-who-sees-a-restricted-item.md)). No route answers outside access by a path of its own.
2. **Off until switched on.** Each kind is an integration ([grantr ADR-0034](../grantr/adr/0034-integrations-switched-per-tenant-and-workspace-in-grantrs-table-audited.md)): `sharing:guests`, `sharing:links`, `sharing:public_forms` and `sharing:portals`. The deployment can leave one uninstalled, and a tenant's or workspace's admins switch each on.
3. **Narrow by construction.** An outsider holds only what was granted on named items, never a tenant-wide listing, and never a `grantr:` action.
4. **Everything expires, or says why it doesn't.** Guest grants and links have an expiry by default, which the tenant bounds.
5. **Audited and revocable from one place.** Every invitation, grant, link, open, submission and expiry is in grantr's audit log, marked as outside access. One admin page lists and revokes them all.
6. **People decide, agents propose.** An agent may draft an invitation or a link as a proposal; a person accepts it.

### Guests

([#1119](https://github.com/alexnodeland/lattice/issues/1119))

A **guest** is a user whose membership in a tenant is the new built-in tenant role `guest`, rather than `member`.

| Role | On | Holds |
|---|---|---|
| `guest` | a tenant | `grantr:read_shared`: listing the items granted to the caller themselves, or to a group they are in. No other action |
| `participant` | a workspace, thread or artifact | a viewer's, and `artifactr:post_message`, `artifactr:answer_deferred`, and `artifactr:create_artifact` of kind `submission`. No edits, no proposals to resolve, no `artifactr:use_model` |

- **The resolver admits guests.** [grantr ADR-0005](../grantr/adr/0005-a-users-tenants-from-grantrs-memberships.md)'s membership check accepts `member` or `guest`, and the actor it answers says which. A user can be a member of one tenant and a guest in another. portalr's tenant switcher marks a guest tenant "Guest".
- **A guest lists nothing tenant-wide.** `guest` doesn't hold `artifactr:read_workspaces`, so the workspace listing refuses. Members, groups and keys are refused as for any non-admin. `grantr:read_shared` answers the threads, artifacts and workspaces granted to them directly or through a group, which is the guest's home.
- **Grants a guest may hold** are capped by a tenant setting ([lattice ADR-0030](../adr/0030-settings-typed-declared-in-lattice-core-and-only-narrowed-below.md)), `sharing.guest_max_role`: `viewer`, `participant` (the default) or `editor`. Never `admin`, never a custom role holding any `grantr:` action, and never a grant on the tenant. A grant above the cap is `Invalid`, as is any grant to a guest on a workspace when `sharing.guest_workspaces` is off (the default).
- **Expiry.** A grant gains an optional `expires_at`. A grant to a guest must have one, at most `sharing.guest_max_days` (default 90) ahead. A check after `expires_at` treats the grant as absent, so a check still writes nothing ([grantr ADR-0015](../grantr/adr/0015-a-check-writes-nothing.md)). The deployment's own tools ([grantr ADR-0021](../grantr/adr/0021-the-deployments-own-tools.md)) sweep expired grants, recording `GrantExpired` for each and removing a guest with no grants left. Removal runs the member-removal hooks ([grantr ADR-0036](../grantr/adr/0036-a-hook-on-a-members-removal.md)). `renew(grant, expires_at)` extends a grant within the cap.
- **Inviting** is one command, `invite_guest(tenant, email, grants, by=...)`. It needs the new action `grantr:invite_guest` on every item named. The workspace's `admin`, and the tenant's `owner` and `admin`, hold it; a tenant may give it to editors through a custom role. In one transaction it makes the membership and the grants, and it records `GuestInvited`. The email goes through portalr's existing invitation, Supabase Auth's admin API ([portalr ADR-0024](../portalr/adr/0024-access-members-groups-and-keys.md)). A tenant may also limit guests to email domains, with `sharing.guest_domains`.
- **Restricted items.** A grant on the item holds as ever ([grantr ADR-0024](../grantr/adr/0024-who-sees-a-restricted-item.md)). Inviting a guest to a restricted item also needs `grantr:restrict` on it, so only those who may see who sees it can widen it.
- **Seeing people.** A guest isn't a member, so [portalr ADR-0038](../portalr/adr/0038-people-by-email.md)'s people route gives them no member's email. They see the authors of messages in threads they can read, by a display name (a profile field this adds), never by email, and members see guests by email marked "Guest".
- **Agents acting for a guest.** An agent turn acts for its user ([grantr ADR-0004](../grantr/adr/0004-an-agent-turn-acts-for-its-user.md)), so it holds what the guest holds. Its workspace-wide tools (search across the workspace, knowledge recall, data spaces) are filtered by the same check, and refuse what the guest can't read. Whether a guest's message starts an agent turn is a workspace setting, `sharing.guest_agent`, off by default. `participant` doesn't hold `artifactr:use_model`, so the workspace's default model answers and the workspace pays for it.
- **Removing** a guest revokes every grant they hold in the tenant, at once, through the member-removal path.

### Share links

([#1120](https://github.com/alexnodeland/lattice/issues/1120))

A **link** is a new subject kind, `Link`. It is a grantee with one grant of the built-in role `link_viewer` on one artifact. `link_viewer` holds that artifact's reads and `open`, and nothing else: no thread, no listing, no feedback.

```python
class Link(BaseModel, frozen=True):
    kind: Literal["link"] = "link"
    id: LinkId  # 8 bytes, hex: the public half
```

- **The token** is `lattice_ln_<id>_<secret>`, with 32 random bytes as the secret, the shape of a key's. grantr stores the id, the tenant, the artifact, the options and a SHA-256 digest of the secret, as it does a key's. A link is shown once at creation and can be copied again only by recreating it.
- **Pinned or live.** A link names the artifact and either `version=None` (the head, updating live) or one version (frozen). A frozen link keeps showing its version after the artifact changes or is archived. A deleted artifact ends every link to it.
- **Options:**
  - `expires_at`: required, at most `sharing.link_max_days` ahead (default 30);
  - `passcode`: stored as an Argon2id hash, with five tries per link and address per 15 minutes;
  - `download`: whether a native file's bytes may be downloaded, or only its rendered pages viewed (off by default);
  - `watermark`: the link's label drawn over rendered pages.
- **Making a link** needs the new action `grantr:create_link` on the artifact. The workspace's `admin`, and the tenant's `owner` and `admin`, hold it; custom roles may give it to editors. A restricted artifact also needs `grantr:restrict`. `create_link`, `revoke_link` and `links(tenant, artifact=None)` are grantr commands, and record `LinkCreated` and `LinkRevoked`.
- **Opening a link.** portalr serves `/s/<token>` outside the tenant's shell. `GET /portalr/v1/shared` reads the token from an `Authorization: Link <token>` header, never from a logged query string. The resolver answers the `Link` subject in the link's tenant, and every read is checked against it as any subject is. The page shows the artifact with the app's own renderers, read-only, with no navigation into the tenant. Live links receive the artifact's updates over a WebSocket scoped to that one artifact.
- **Opens are audited.** `LinkOpened` records the link, the time, a truncated address (a /24 for IPv4, a /48 for IPv6) and the user agent's family, never the full address. It is kept for as long as the retention policy says (#1046). Owners are told about the first open (#1122).
- **Headers:** `Referrer-Policy: no-referrer`, `X-Robots-Tag: noindex`, `Cache-Control: no-store`, and the app's CSP, so a token isn't leaked or indexed.
- **Rate limits** per link and per address, and a generic "This link isn't available" for an unknown, revoked, expired or wrong token alike, so links can't be probed.
- **Data classes.** Until #1044 lands, a link can't be made to an artifact in a restricted thread unless its maker holds `grantr:restrict` there. Once #1044 lands, each class declares `may_leave_tenant`, and a link to an artifact with a class that may not is `Invalid`.

### Public forms

([#1121](https://github.com/alexnodeland/lattice/issues/1121))

A form artifact ([lattice RFC-0005](0005-forms-dashboards-and-mini-apps.md)) gains `public: bool`. A public form is reached by a link with the role `link_submitter`. That role holds `open` and `read` on the form, and `artifactr:create_artifact` of kind `submission` on that form alone.

- **Submission policies.** `once` and `per_person` need an identity, so a public form takes `many`. `per_email` (one submission per verified email address, by a one-time code) comes once notifications can send email (#952).
- **Attribution.** A submission's actor is the link's subject, `link:<id>`. What the submitter chose to give (a name, an email, if the form asks) is in its data like any field. ui_checks run as now: the form is open, the version is the head's, the values are valid, and the id is its derivation, with the nonce of `many`.
- **Abuse controls**, all before a submission is created:
  - rate limits per address and per form, set per workspace, with defaults;
  - a captcha, through a `Captcha` port with Cloudflare Turnstile and hCaptcha adapters chosen by the operator. Without an adapter configured, a form can't be made public unless the operator sets `captcha: none` knowingly;
  - a size limit on the whole submission, and no file fields on public forms in this RFC;
  - spam scoring through the `decide` port (#1024), when it's present. A submission it flags is created with `held: true`.
- **Held submissions** are listed for the form's editors, who release or delete each. relayr bridges `ui:form_submitted` for a submission only once it's released, so rules never act on spam.
- **Data class.** Submissions to a public form take the workspace's class for personal data (#1044) by default, since they usually carry contact details.

### Client portals

([#1121](https://github.com/alexnodeland/lattice/issues/1121))

A **portal** is the guest home for one outside party, given a name and a face:

- **An outside group.** A grantr group gains `outside: bool`. An outside group holds only guests, and the guest caps apply to its grants. Grants made to it reach every guest in it.
- **A portal** belongs to a tenant and has a `slug`, a name, an outside group, and a brand kit ([lattice RFC-0007](0007-portalr-brand-kits.md)), the tenant's by default. It lives at `/p/<tenant>/<slug>`. Its page lists what `grantr:read_shared` answers for the group, grouped by kind, with recent activity in the threads shared with it.
- **Nothing new is shared by a portal:** it's a view of the group's grants. Revoking a grant removes an item from the portal; removing a guest from the group removes them from it.
- Custom domains for portals wait for brand kits per tenant, and are an unresolved question.

### portalr, portr and admin

([#1122](https://github.com/alexnodeland/lattice/issues/1122))

- **The Share dialog**, which the app has today for members and groups, gains guests by email (with a role and an expiry), links (with their options), and a form's "Make public". It shows everyone who holds access to the item and how, members, guests and links alike, each with a revoke button.
- **A guest's shell** has only their home ("Shared with you"), the items in it, and their profile. It has no workspace list, members directory, admin, or search beyond what they can read, and it is clearly marked with the tenant they are in.
- **Admin's "Outside access"** sits beside Members, Groups and Keys ([portalr ADR-0024](../portalr/adr/0024-access-members-groups-and-keys.md)), and lists:
  - each guest: what they can reach, who invited them, when they were last seen and when they expire;
  - each link: its artifact, options, number of opens and last open;
  - each public form: its submissions and held count;
  - each portal;
  - and, for every list, filters, bulk revoke, and a CSV export for access reviews (#1051).
- **Notices** (through #952 once it lands; in the app's activity until then):
  - a link's first open;
  - a guest's access expiring within seven days, sent to whoever invited them;
  - a guest posting in a thread;
  - held submissions waiting.
- **portr** serves the same share tools over MCP and ACP, behind the same checks ([#914](https://github.com/alexnodeland/lattice/issues/914)). An agent's `share` tool creates a proposal naming the guest or link, and nothing is shared until a person who may share accepts it.

### Compliance

- **Audit.** Every event above is in grantr's audit log, typed, with `outside: true`, and included in the tamper-evident chain (#1049).
- **Data subject requests.** A guest is a data subject like any user. Their messages and submissions are reached by access and erasure requests (#1045), and a public submitter's by the email they gave.
- **Retention.** Link opens, held submissions and expired guests' records follow retention per class (#1046).
- **The control matrix** (#1043) lists outside access, its switches and its evidence.
- **HIPAA mode** (#1055) turns off links and public forms, and keeps guests only where the operator allows them.

### Errors

| Case | Answer |
|---|---|
| The integration is off in the tenant or workspace | `Refused`, naming the switch |
| A grant to a guest above `sharing.guest_max_role`, without an expiry, past the cap, or on the tenant | `Invalid`, naming the setting |
| A guest's email outside `sharing.guest_domains` | `Invalid` |
| Inviting to, or linking, a restricted item without `grantr:restrict` | `Refused` |
| An unknown, revoked, expired or wrong token, or a wrong passcode | "This link isn't available", the same for each; the passcode case is counted toward its limit |
| A public form over its rate limit, or with a failed captcha | 429, or 422 naming the captcha, before anything is stored |
| A guest's agent turn when `sharing.guest_agent` is off | The message is posted, and the guest is told no agent answers here ([artifactr ADR-0095](../artifactr/adr/0095-a-run-that-waits-on-nothing-is-failed-and-a-message-that-starts-nothing-is-told.md)) |

## Drawbacks

- **The first break in "members only".** Every listing and read path has assumed a member. Each needs testing against a guest and a link, and `grantr.testing.matrix` grows two subjects.
- **More to administer.** Expiries, renewals and held submissions need someone to look after them; notices and the admin page are the mitigation, not a cure.
- **Public surfaces attract abuse.** Links and public forms are reachable from the internet without sign-in, so rate limits, captchas and spam scoring are part of the design, and operators carry the cost of a captcha provider.
- **Grants with expiry** add a time dependency to a check that has none today, so tests need a clock.

## Alternatives

- **Outsiders as members with a minimal custom role.** They would still hold `member`, so they could list workspaces and see members, and nothing would expire. The tenant boundary is the wrong one.
- **A separate tenant per client.** This duplicates workspaces and agents, and nothing can be shared across tenants.
- **Signed URLs to blobs instead of links.** There is no revocation short of rotating keys, no audit of opens, no live view, and nothing for data that isn't a blob.
- **Links that reach a whole thread.** These are useful, but a thread carries the agent's tool calls and other people's words, so they wait until per-message redaction exists. A guest covers the case.
- **An outside form service, through connectors.** The form, its schema and its submissions would then live outside lattice's permissions, provenance and retention.
- **Native mobile or email-only participation.** This is out of scope. A guest uses the same app, and email replies arrive with #952's connectors.

## Unresolved questions

- Should guests see other guests in the same thread by email, or only by display name?
- Do portals get custom domains, and do they wait for per-tenant brand kits?
- Should a guest's agent turns be paid for by the workspace, or need a separate budget (#1126)?
- Should `editor` be allowed for guests at all, or only `participant`, until proposals from guests are designed?
- Should email-verified links (an allowed domain with a one-time code) come before `per_email` forms, sharing their verification?

## Tracking

- [ ] grantr ADR: the `guest` and `participant` roles, grant expiry, `invite_guest`, `read_shared` and the resolver's change (#1119).
- [ ] grantr ADR: the `Link` subject, `link_viewer` and `link_submitter`, and link commands (#1120).
- [ ] grantr and portalr: guests end to end, with the matrix and scenarios (#1119).
- [ ] portalr: share links, the `/s/` page, opens audited (#1120).
- [ ] artifactr.ui and relayr.ui: public forms, the `Captcha` port, held submissions (#1121).
- [ ] grantr and portalr: outside groups and portals (#1121).
- [ ] portalr and portr: the Share dialog, the guest's shell, Outside access in admin, notices (#1122).
