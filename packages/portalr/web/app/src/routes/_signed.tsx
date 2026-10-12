import { Button } from "@portalr/ui";
import { createFileRoute, Outlet, redirect, useNavigate } from "@tanstack/react-router";

/** Every route but signing in: each needs someone signed in, who can sign out. */
export const Route = createFileRoute("/_signed")({
  beforeLoad: async ({ context }) => {
    if (!(await context.signed.signedIn())) {
      throw redirect({ to: "/sign-in" });
    }
  },
  component: Signed,
});

function Signed() {
  const { signed, queryClient } = Route.useRouteContext();
  const navigate = useNavigate();

  async function signOut() {
    await signed.auth.signOut();
    queryClient.clear();
    await navigate({ to: "/sign-in" });
  }

  return (
    <>
      <header className="mb-6 flex justify-end">
        <Button variant="secondary" onClick={signOut}>
          Sign out
        </Button>
      </header>
      <Outlet />
    </>
  );
}
