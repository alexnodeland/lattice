import { Button, Lockup, TextField } from "@portalr/ui";
import { createFileRoute, redirect, useNavigate } from "@tanstack/react-router";
import { useActionState } from "react";

export const Route = createFileRoute("/sign-in")({
  head: () => ({ meta: [{ title: "Sign in · portalr" }] }),
  beforeLoad: async ({ context }) => {
    if ((await context.signed.signedIn()) !== null) {
      throw redirect({ to: "/" });
    }
  },
  component: SignIn,
});

interface Attempt {
  readonly email: string;
  readonly refused: string | null;
}

/** Sign in with an email and a password, through Supabase Auth. */
function SignIn() {
  const { signed } = Route.useRouteContext();
  const navigate = useNavigate();
  const [attempt, signIn, pending] = useActionState(
    async (_last: Attempt, form: FormData): Promise<Attempt> => {
      const email = String(form.get("email"));
      const { error } = await signed.auth.signInWithPassword({
        email,
        password: String(form.get("password")),
      });
      if (error) {
        return { email, refused: error.message };
      }
      await navigate({ to: "/" });
      return { email, refused: null };
    },
    { email: "", refused: null },
  );

  return (
    <main id="main" className="grid min-h-dvh place-items-center bg-paper px-4 py-10 text-fg">
      <div className="flex w-full max-w-sm flex-col gap-2 rounded-xl border border-line bg-surface p-8">
        <Lockup className="mb-6 h-9" />
        <h1 className="font-bold text-2xl tracking-tight">Sign in</h1>
        <p className="mb-4 text-muted text-sm">with your email and password</p>
        <form className="flex flex-col gap-4" action={signIn}>
          <TextField
            label="Email"
            name="email"
            type="email"
            autoComplete="email"
            defaultValue={attempt.email}
            required
          />
          <TextField
            label="Password"
            name="password"
            type="password"
            autoComplete="current-password"
            error={attempt.refused}
            required
          />
          <Button type="submit" disabled={pending} className="mt-1 py-2">
            {pending ? "Signing in" : "Sign in"}
          </Button>
        </form>
      </div>
    </main>
  );
}
