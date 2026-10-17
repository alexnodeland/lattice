/**
 * What `Markdown` may draw beyond its basics, each an add-on a workspace can turn off. GitHub's
 * Markdown, code blocks and callouts are always on; an add-on that is off, or that `ui` can't draw
 * yet, shows its source, with one quiet line that says so, and never nothing (portalr ADR-0043).
 *
 * The values come from the page: the app gives a workspace's integrations here through
 * `AddonsProvider`, as grantr answers them, deployment ∧ tenant ∧ workspace (lattice ADR-0027,
 * grantr ADR-0034), each add-on its integration's default until they are read, and where they
 * can't be (portalr ADR-0045). Without a provider, as in admin, it is the defaults below.
 */

import { createContext, type ReactNode, useContext } from "react";

/** Each add-on, and whether it is on. */
export type Addons = {
  /** Math, `$$…$$` and `math` fences, drawn as MathML (portalr ADR-0044). */
  readonly math: boolean;
  /** Mermaid's diagrams: parked, since Mermaid can't draw under the CSP (portalr ADR-0042). */
  readonly mermaid: boolean;
};

/** Each add-on's integration's default, as lattice's registry declares it: math on, and diagrams off. */
const DEFAULT_ADDONS: Addons = { math: true, mermaid: false };

const Context = createContext<Addons>(DEFAULT_ADDONS);

/** Which add-ons the Markdown inside may draw. */
export function AddonsProvider({ value, children }: { value: Addons; children: ReactNode }) {
  return <Context value={value}>{children}</Context>;
}

/** The add-ons this Markdown may draw. */
export function useAddons(): Addons {
  return useContext(Context);
}
