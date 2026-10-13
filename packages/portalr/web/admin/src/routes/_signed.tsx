import { createFileRoute, Outlet, redirect } from "@tanstack/react-router";

/**
 * Every route but signing in: each needs someone signed in, whom its context names. Each frames
 * itself, with the account in it: a plain page, or a tenant's or the deployment's frame.
 */
export const Route = createFileRoute("/_signed")({
  beforeLoad: async ({ context }) => {
    const user = await context.signed.signedIn();
    if (user === null) {
      throw redirect({ to: "/sign-in" });
    }
    return { user };
  },
  component: Outlet,
});
