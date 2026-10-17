/** Who is signed in, as every signed-in screen offers them: their scheme, colour-blind friendly charts, and signing out. */

import type { Signed } from "@portalr/client";
import { AccountMenu } from "./account-menu";
import { useAppearance } from "./appearance";
import { useColourBlind } from "./colour-blind";

/** The account menu for the session `signed` holds: its email, its scheme, and signing out. */
export function Account({ signed }: { signed: Pick<Signed, "email" | "signOut"> }) {
  const [appearance, setAppearance] = useAppearance();
  const [colourBlind, setColourBlind] = useColourBlind();
  return (
    <AccountMenu
      name={signed.email() ?? "Signed in"}
      appearance={appearance}
      onAppearance={setAppearance}
      colourBlind={colourBlind}
      onColourBlind={setColourBlind}
      onSignOut={() => void signed.signOut()}
    />
  );
}
