/**
 * What `Markdown` may draw beyond its basics, each an add-on a workspace can turn off. GitHub's
 * Markdown, code blocks and callouts are always on; an add-on that is off, or that `ui` can't draw
 * yet, shows its source, with one quiet line that says so, and never nothing (portalr ADR-0043).
 * Each follows its integration, as the page answers it through `IntegrationsContext` (portalr
 * ADR-0045, ADR-0047): math by default on, and diagrams off.
 */

import { use } from "react";
import { IntegrationsContext } from "./integrations";

/** Each add-on, and whether it is on. */
interface Addons {
  /** Math, `$$…$$` and `math` fences, drawn as MathML (portalr ADR-0044). */
  readonly math: boolean;
  /** Mermaid's diagrams: parked, since Mermaid can't draw under the CSP (portalr ADR-0042). */
  readonly mermaid: boolean;
}

/** The add-ons this Markdown may draw. */
export function useAddons(): Addons {
  const isEnabled = use(IntegrationsContext);
  return { math: isEnabled("markdown:math"), mermaid: isEnabled("markdown:mermaid") };
}
