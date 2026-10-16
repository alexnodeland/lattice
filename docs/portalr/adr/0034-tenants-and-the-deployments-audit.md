# ADR-0034: Tenants in admin, created by email, and the deployment's audit log

**Status:** Accepted, amended by [ADR-0038](0038-people-by-email.md)
**Date:** 2026-10-16
**Deciders:** Alex Nodeland
**Amends:** [RFC-0002](../../rfcs/0002-portalr-the-portal.md), whose operator Tenants row has creating a tenant and its owner without saying how the owner is named, and whose admin areas have no deployment audit log

## Context

lattice RFC-0002 gives admin two areas for the deployment's operators, Tenants and Tools. This is the first, Tenants (6e-i); Tools follow (6e-ii).

What exists:

- `GET /portalr/v1/deployment/tenants` gives grantr's tenants and, from one LiteLLM team list, each team's spend. Only operators (`portalr:read_deployment`) may read it, which is also how admin tells who is one ([ADR-0023](0023-admins-shell-and-home.md)). admin's `/deployment` has Home alone.
- grantr's `create_tenant(tenant, owner=<user id>, by=)` is checked by `grantr:create_tenant`, an operator's alone, inside one transaction that refuses a tenant that exists. Its audit entry, `tenant_created`, goes in the new tenant's own log.
- portalr's `POST /v1/invites` invites a member through Supabase Auth, which creates the person or finds them, using the admin key the application holds.
- grantr's `GET /audit` is the deployment's own log, readable with `grantr:grant_operator`: operators made and revoked.

The user decided:

1. A new tenant's owner is named by email.
2. Operators list and create tenants, and nothing more: no deleting, no granting operators, no creating a LiteLLM team. A tenant with no team shows no budget.
3. A deployment audit view over grantr's `GET /audit`.
4. Tenants is its own pull request, with the owner route, the page and the audit view.

## Decision

- **`POST /portalr/v1/deployment/tenants {tenant, owner_email}` creates a tenant with its owner invited or found by email,** for operators. It exists where the application gives portalr its `invite`, as `POST /v1/invites` does, and answers 201 with `{tenant, owner}`: the tenant and the owner's user id, never the email.
  - **The checks come before anyone is asked about.** The caller must read the deployment (`portalr:read_deployment`, which is the operator dependency every deployment route has) and may create tenants (`grantr:create_tenant`); the email must look like one; and the tenant must not exist. Only then is Supabase Auth asked to invite or find the owner, and then grantr creates the tenant, which checks `grantr:create_tenant` again.
  - **A repeated request creates nothing twice and invites no one again.** A tenant that exists is refused before Supabase is asked, as `invalid` (422), "`<tenant>` exists"; and grantr refuses a second creation in its own transaction, so two requests that race can't make two tenants. A request that raced past the first check may find the owner twice: Supabase's find-or-create makes that harmless, and it sends an email to a new person once.
  - **The email is not logged, and not echoed.** The route logs nothing, a malformed email is refused by hand rather than by the model's validation, whose error would repeat the value, and no answer, refusal or invite failure names it. A test holds it against a log capture and against each refusal.
  - **Failures:** a caller who isn't an operator, or who may not create tenants, is 403; an email that isn't one, a tenant id that isn't one, or a tenant that exists, is 422; Supabase not inviting or finding the owner is 502 `invite_failed`, with no tenant made.
- **Tenants is `/deployment/tenants`,** on the deployment rail of an operator, gated by the deployment's layout, which lets in only whoever reads the deployment.
  - It lists every tenant by name, with its spend, and its budget in words: the amount and its period and how much is spent; "No budget set" for a team without one; "No budget" for a tenant with no team; and a dash where LiteLLM didn't answer, with a note that spend isn't shown, so a LiteLLM that is down or absent leaves the list.
  - The list pages on the client, fifty at a time, for up to a few hundred tenants, with "Show more" and a count for screen readers.
  - Tenants aren't entered from here. admin opens a tenant to its own owners and admins, and an operator who isn't a member of one doesn't get in (the RFC's model, [ADR-0005](0005-operators-see-across-tenants.md)).
- **A tenant is created from a form, after a confirmation.**
  - Its two fields, the tenant and the owner's email, enable "Create tenant" once they look right. It opens an alert dialog that says the tenant and the owner, that Supabase Auth invites the owner if they have no account and finds them if they do, and that a tenant can't be deleted from here.
  - The action is sent once however often it is submitted while under way, and the dialog can't be dismissed meanwhile ([ADR-0032](0032-runs-in-admin.md)). A refusal is said in the dialog, which stays.
  - On success the form is emptied, the list is read again, a status says "`<tenant>` is created, owned by `<user id>`", and focus goes to the form's first field, since the trigger is then disabled.
  - The email is kept nowhere in the browser: not in a query key or the cache, not in the address or storage, and not on the page once the tenant is made. A test checks storage and the page.
- **The deployment's audit log is `/deployment/audit`.** It lists, newest first and a page back at a time, what grantr's `GET /audit` gives, with the same sentences and names as a tenant's Audit: who was made an operator, who stopped being one, by whom and when. It needs `grantr:grant_operator`, which operators hold; its failure is a way on. A tenant's creation is not in it, for now: grantr keeps `tenant_created` in the new tenant's own log, where its owner reads it. A follow-up change to grantr, its own pull request, makes it also write a deployment-scoped entry (who made which tenant); once that lands, this view shows creations, and not before: it is not changed for it here.
- **Amended 2026-10-16:**grantr now writes that entry, `deployment_tenant_created`, naming the tenant, its owner and who created it ([grantr ADR-0033](../../grantr/adr/0033-a-tenants-creation-in-the-deployments-log.md)), and this view shows it: "created the tenant acme, owned by ada@acme.test", by the operator who did; its type reads "Tenant created (deployment)" in a type filter. Tenants created before that have no such entry.
- **`ConfirmDialog`** can be disabled until what it acts on is filled in, and can send focus somewhere else than its trigger once the action is done (`finalFocus`); cancelling, Escape and the backdrop return it to the trigger as ever.
- **Home's areas are Home, Tenants and Audit.**

## Options considered

| Option | For | Against |
|---|---|---|
| **Owner by email, through Supabase Auth (chosen)** | An operator knows an email, not a user id; the route's invitation is the members' | A new operator-only route, and the Supabase admin key on it |
| Owner by user id | No new server code | No operator knows one: it is Supabase's id |
| Check, then invite (chosen) | No one is invited by a caller who may not, or for a tenant that exists | A second check of the tenant, which grantr's transaction makes the real one |
| Invite, then create, with no check first | One less read | Every refused creation, such as one for a tenant that exists, has invited someone and sent an email |
| **Confirm every creation (chosen)** | A tenant is a lasting thing, with a person given ownership of it and perhaps an email sent | One more step |
| Create at once | Quick | A mistyped id or email can't be taken back from here |
| Delete tenants too | A whole life cycle | grantr deletes only what it holds: every library's data would stay, orphaned |

## Consequences

- Easier: an operator makes a tenant for someone from their email, without a command line, and sees every tenant and its spend in one place.
- Easier: changes to who operates the deployment are readable in the UI.
- Harder: the owner route holds an email for the length of a request, and an application without Supabase's admin API has no route.
- Accepted: a tenant with no LiteLLM team shows no budget until someone sets one outside admin.
- Accepted: **an invited user, and the email sent to them, can outlive a refused creation.** The checks come before Supabase is asked, which keeps most refusals from inviting anyone, but a creation can still fail after the invitation: a lost race on the tenant's name, the operator's grant revoked in between, or a storage error, which is answered 503 with nothing of what storage said. Supabase invitations are not rolled back; the person has an account and no membership, and inviting them again to anything finds them.
- Accepted: **an operator can learn whether an email has an account, and its user id.** The route answers the owner's user id for an email, and a new person and an existing one take different time (Supabase sends an email to the first). Operators are trusted with every tenant, and the members invite route tells a tenant's admins the same.
- Accepted: **the route has no rate limit,** though it can send invitation emails. It is operator-only, sends one at most per request, and each needs a tenant name that doesn't exist yet. A deployment that wants a limit puts it on the route at its proxy.
- Supabase normalises an email's case and unicode, and decides whether two spellings are one person; plus-addressing (`dan+x@initech.com`) stays a distinct address. portalr does not normalise it again: Supabase's answer, the user id, is the authority.
