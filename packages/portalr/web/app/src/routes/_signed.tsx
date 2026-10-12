import { Button } from "@portalr/ui";
import { createFileRoute, Outlet, redirect } from "@tanstack/react-router";

/** Every route but signing in: each needs someone signed in, whom its context names. */
export const Route = createFileRoute("/_signed")({
  beforeLoad: async ({ context }) => {
    const user = await context.signed.signedIn();
    if (user === null) {
      throw redirect({ to: "/sign-in" });
    }
    return { user };
  },
  component: Signed,
});

/** Signing out ends the session here; `Signed` then clears what was read and goes to sign in. */
function Signed() {
  const { signed } = Route.useRouteContext();
  return (
    <>
      <header className="mb-6 flex justify-end">
        <Button variant="secondary" onClick={() => signed.signOut()}>
          Sign out
        </Button>
      </header>
      <Outlet />
    </>
  );
}
