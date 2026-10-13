/** Who is signed in, as every signed-in screen offers them: their scheme, and signing out. */

import { AccountMenu } from "@portalr/ui";
import { useAppearance } from "./appearance";
import type { Signed } from "./signed";

export function Account({ signed }: { signed: Signed }) {
  const [appearance, setAppearance] = useAppearance();
  return (
    <AccountMenu
      name={signed.email() ?? "Signed in"}
      appearance={appearance}
      onAppearance={setAppearance}
      onSignOut={() => void signed.signOut()}
    />
  );
}
