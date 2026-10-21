import { pageTitle, SignIn } from "@portalr/ui";
import { createFileRoute, redirect, useNavigate } from "@tanstack/react-router";

export const Route = createFileRoute("/sign-in")({
  head: ({ match }) => ({
    meta: [{ title: pageTitle(match.context.config.brand, "app", "Sign in") }],
  }),
  beforeLoad: async ({ context }) => {
    if ((await context.signed.signedIn()) !== null) {
      throw redirect({ to: "/" });
    }
  },
  component: SigningIn,
});

/** Sign in with an email and a password, through Supabase Auth. */
function SigningIn() {
  const { signed } = Route.useRouteContext();
  const navigate = useNavigate();
  return (
    <SignIn
      onSignIn={async (email, password) => {
        const { error } = await signed.auth.signInWithPassword({ email, password });
        if (error) {
          return error.message;
        }
        await navigate({ to: "/" });
        return null;
      }}
    />
  );
}
