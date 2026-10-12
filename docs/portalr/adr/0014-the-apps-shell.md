# ADR-0014: The app's shell: English strings, a committed route tree, and Supabase Auth's client

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

Phase 5 builds the app's first screens: signing in, and choosing a tenant and a workspace. portalr RFC-0001 left localization to be settled before them. lattice RFC-0002 chose TanStack Router's file-based routes, whose route tree a Vite plugin generates, and Supabase Auth's client alone for signing in.

## Decision

- **The strings are English, in the components.** There is no catalog until a second language is wanted, when one goes in with it, and the strings move then.
- **The route tree is committed.** `src/routeTree.gen.ts` is what TanStack Router's Vite plugin writes from `src/routes/`, so the typecheck and knip see the routes without a build. A test generates it again beside the committed one and fails if they differ, as each package's drift test does; `moon run app:build` rewrites it. Biome leaves it alone.
- **Signing in is `@supabase/auth-js`,** the auth client `@supabase/supabase-js` wraps, without the rest. It keeps the session in `localStorage` under `portalr`, refreshes the token, and every request carries the current one, with the tenant the route names (`client`'s `Session`, whose tenant is null before one is chosen).
- **The shell's routes:** `/sign-in`; then, signed in, `/`, which lists a person's tenants from grantr's `/me` (they have no access with none, and go straight to their only one); `/t/$tenant`, the workspaces grantr says they can open there; and `/t/$tenant/w/$workspace`, which the app's areas open into.
- **A password signs in, for now.** Magic links and the deployment's own providers come with phase 7, where the template's Supabase can send mail and its scenarios can follow a link.

## Options considered

| Option | For | Against |
|---|---|---|
| **English in the components (chosen)** | Nothing to keep in step until a translation exists | Moving the strings later touches every screen |
| A catalog from the start (Lingui) | Ready for a second language | A build step and a convention for one language |
| **A committed route tree (chosen)** | Types and knip work from a clean checkout | A generated file in review, held by a test |
| Generating it at build | Nothing generated in git | `typecheck` and `knip` need a build first |
| `@supabase/supabase-js` | One client for everything Supabase | The UIs use its auth alone |

## Consequences

- Easier: a route's params and loader data are typed from the committed tree.
- Harder: a route added without regenerating the tree fails the test until `moon run app:build` runs.
- Harder: until phase 7, the app offers a password alone.
