/** Signing in, as app and admin both open: a card with the UI's lockup, an email and a password. */

import { useActionState } from "react";
import { Button } from "./button";
import { Lockup, type Ui } from "./marks";
import { TextField } from "./text-field";
import { TYPE } from "./type";

interface Attempt {
  readonly email: string;
  readonly refused: string | null;
}

/**
 * Sign in with an email and a password. `onSignIn` answers why it was refused, or null once the
 * person is signed in, when the caller goes on.
 */
export function SignIn({
  ui = "app",
  onSignIn,
}: {
  ui?: Ui;
  onSignIn: (email: string, password: string) => Promise<string | null>;
}) {
  const [attempt, signIn, pending] = useActionState(
    async (_last: Attempt, form: FormData): Promise<Attempt> => {
      const email = String(form.get("email"));
      return { email, refused: await onSignIn(email, String(form.get("password"))) };
    },
    { email: "", refused: null },
  );
  return (
    <main id="main" className="grid min-h-dvh place-items-center bg-paper px-4 py-10 text-fg">
      <div className="flex w-full max-w-sm flex-col gap-2 rounded-(--sign-in-radius) border border-line bg-surface p-(--sign-in-pad)">
        <Lockup ui={ui} className="mb-6 h-9" />
        <h1 className={TYPE.page}>Sign in</h1>
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
