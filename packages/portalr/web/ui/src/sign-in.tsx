/** Signing in, as app and admin both open: a card with the UI's lockup, an email and a password. */

import { useActionState } from "react";
import { useBrand } from "./brand";
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
  const brand = useBrand();
  const [attempt, signIn, pending] = useActionState(
    async (_last: Attempt, form: FormData): Promise<Attempt> => {
      const email = String(form.get("email"));
      return { email, refused: await onSignIn(email, String(form.get("password"))) };
    },
    { email: "", refused: null },
  );
  return (
    // A card from the small breakpoint; on a phone the form is the page, on its 16px gutter
    // (portalr ADR-0085). The lockup keeps its inks here alone.
    <main id="main" className="grid min-h-dvh place-items-center bg-paper px-4 py-10 text-fg">
      <div className="flex w-full min-w-0 max-w-sm flex-col gap-2 rounded-(--sign-in-radius) border border-line bg-surface p-(--sign-in-pad) max-sm:border-0 max-sm:bg-transparent max-sm:p-0">
        <div className="mb-6 flex flex-col gap-1">
          <Lockup ui={ui} className="h-9 self-start" />
          {brand?.copy?.tagline && (
            <p dir="auto" className="text-muted text-sm">
              {brand.copy.tagline}
            </p>
          )}
        </div>
        <h1 dir="auto" className={TYPE.page}>
          {brand?.copy?.signIn ?? "Sign in"}
        </h1>
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
          <Button type="submit" pending={pending} className="mt-1">
            {pending ? "Signing in" : "Sign in"}
          </Button>
        </form>
      </div>
    </main>
  );
}
