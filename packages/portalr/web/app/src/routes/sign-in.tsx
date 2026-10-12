import { Button, Page, TextField } from "@portalr/ui";
import { createFileRoute, redirect, useNavigate } from "@tanstack/react-router";
import { type FormEvent, useState } from "react";

export const Route = createFileRoute("/sign-in")({
  beforeLoad: async ({ context }) => {
    if (await context.signed.signedIn()) {
      throw redirect({ to: "/" });
    }
  },
  component: SignIn,
});

/** Sign in with an email and a password, through Supabase Auth. */
function SignIn() {
  const { signed } = Route.useRouteContext();
  const navigate = useNavigate();
  const [refused, setRefused] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const { error } = await signed.auth.signInWithPassword({
      email: String(form.get("email")),
      password: String(form.get("password")),
    });
    if (error) {
      setRefused(error.message);
      return;
    }
    await navigate({ to: "/" });
  }

  return (
    <Page title="Sign in">
      <form className="flex max-w-sm flex-col gap-4" onSubmit={submit}>
        <TextField label="Email" name="email" type="email" autoComplete="email" required />
        <TextField
          label="Password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
        />
        {refused && <p role="alert">{refused}</p>}
        <Button type="submit">Sign in</Button>
      </form>
    </Page>
  );
}
