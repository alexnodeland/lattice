/**
 * What `Markdown` may draw beyond its basics, each an add-on a workspace can turn off. GitHub's
 * Markdown, code blocks and callouts are always on; an add-on that is off, or that `ui` can't draw
 * yet, shows its source, with one quiet line that says so, and never nothing (portalr ADR-0043).
 *
 * The values come from the page: today the defaults below; later, the Integrations port that the
 * Excalidraw RFC designs, as deployment ∧ tenant ∧ workspace, which an app gives here through
 * `AddonsProvider`. That port is the seam's other side, and isn't built yet.
 */

import { createContext, type ReactNode, useContext } from "react";

/** Each add-on, and whether it is on. */
export type Addons = {
  /** Mermaid's diagrams: parked, since Mermaid can't draw under the CSP (portalr ADR-0042). */
  readonly mermaid: boolean;
};

/** Until the Integrations port says otherwise: diagrams off. */
const DEFAULT_ADDONS: Addons = { mermaid: false };

const Context = createContext<Addons>(DEFAULT_ADDONS);

/** Which add-ons the Markdown inside may draw. */
export function AddonsProvider({ value, children }: { value: Addons; children: ReactNode }) {
  return <Context value={value}>{children}</Context>;
}

/** The add-ons this Markdown may draw. */
export function useAddons(): Addons {
  return useContext(Context);
}
