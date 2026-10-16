# ADR-0035: People by email, not by id

**Status:** Accepted
**Date:** 2026-10-16
**Deciders:** Alex Nodeland
**Amends:** [ADR-0022](0022-restricting-and-sharing-a-thread.md) and [ADR-0024](0024-access-members-groups-and-keys.md), which name people by grantr's id because nothing portalr read mapped an id to an email

## Context

With real Supabase, a person's grantr id is their auth user's UUID. Admin's Members list, its remove dialog, Groups, Grants and Audit, and the app's Share dialog and chat showed opaque UUIDs ([lattice #169](https://github.com/alexnodeland/lattice/issues/169)); the scenarios passed only because the test application made the id the email's local part. grantr holds no names, only ids and kinds. An email is personal data, so where it comes from, who may see whose, and how long it is kept are decisions, not details.

## Decision

- **The email comes from the application's auth service, through a `people` hook,** `portalr_router(people=)`, as `invite=` is Supabase Auth's admin API. `SupabasePeople` reads `GET /auth/v1/admin/users/{id}` with the project's secret key, which stays in the application. Without a hook, there is no people route, `config.json` says `people: false`, and the UIs show short ids.
- **`GET /portalr/v1/people?id=...` answers the emails of people the caller may see:**
  - **A member of the tenant `X-Tenant` names sees the emails of that tenant's other members.** The caller and every id are checked against grantr's memberships *before* Supabase is asked: an id that is not a member of the tenant is left out without a call, so the route can't be used to find who has an account.
  - **An operator** (`portalr:read_deployment`) **sees anyone's**, with no tenant, so the deployment's own views can name owners.
  - **A key sees no one:** only a person sees people. A caller bound to another tenant's key, or a non-member who is not an operator, is refused (403).
  - **At most 100 ids** (422 beyond, FastAPI's, naming `id`), at least one.
- **The same answer for an id that is unknown, not allowed, or without an email:** it is left out. The answer is `{"people": {id: email}}`, `Cache-Control: no-store`.
- **Fail closed.** A Supabase that is down, slow or answers badly leaves the ids out; the route still answers 200. The UIs show a person with no email by a short id, the first eight characters of a long id such as a UUID (`3f2a91c4…`), never as an error. A service principal is shown by its id.
- **Bounded reads.** `SupabasePeople` reads at most eight users at once, each within three seconds and all of a call within eight, so one request can't hold the application for long. A read that fails or times out is not kept.
- **A short, bounded, in-memory cache** on the server: an email for five minutes, an id with no user or no email for one, at most 2,048 ids, the oldest dropped first. Nothing is written to disk. In the browser, TanStack Query keeps the answer five minutes in memory, for one set of ids, and does not read it again as the window regains focus; it is not persisted.
- **Where emails are, and where they never are.**
  - **Never:** an address, a request's URL (the ids are in it, the emails are not), a log, a span attribute, an error message, `localStorage` or `sessionStorage`, or a stream's or store's state. The chat's messages keep the actors as the server sent them; the author's email is looked up when a message is drawn.
  - The ids in a request's URL are user ids, which grantr and the audit log carry already; the secret key is only on the call to Supabase.
- **Where the UIs show people by email:** admin's Members (list, remove dialog), Groups (members, the member picker, the confirmation of whom a change takes out), Grants (to whom, the form's choices, the revoke dialog, what a grant done says), the tenant's Audit and the deployment's Audit; the app's Share dialog (who holds a role, who may be offered it, the revoke dialog) and a thread's chat (an author who posted without a name of their own). A name a person posted under is shown as it was. The Audit filter still takes an id, since the address holds ids only.
- **The test application names everyone `<id>@portalr.test` but `ghost`,** so a scenario can show an id that Auth does not know.

## Options considered

| Option | For | Against |
|---|---|---|
| **A hook backed by the admin API, checked against grantr's memberships (chosen)** | One place that knows Supabase's admin API, beside the invite; no new store; the caller sees only people they already share a tenant with | One read per id uncached; a cache to keep small |
| An email in the access token's claims for each person | No lookup | Only the signed-in person's own; nothing for the others in a list |
| A profile table portalr or the application keeps | Fast, and ours | A copy of personal data to keep in step and to delete; an application with no such table can't use portalr |
| Any member sees any user's email | Simplest | Reveals who has an account to anyone with a membership |
| Tenant admins alone see emails | Narrowest | The app's Share dialog and chat, which members use, would still show ids |

## Consequences

- Easier: Members, Share, Audit and chat read as people; a first public demo shows no UUIDs.
- Harder: the application wires another hook with the project's secret key, and that key's reach is the same as the invite's.
- Harder: a member of a tenant sees the email of every other member of it, as a member of any team sees the people in it. An owner who does not want that cannot hide a member from the others.
- Harder: an email in the cache outlives its user's deletion by up to five minutes.
- To revisit: a batched lookup, if Supabase offers one; a tenant-level setting for who sees emails.
