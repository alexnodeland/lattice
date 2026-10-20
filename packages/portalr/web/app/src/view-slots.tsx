/**
 * Where a native file's editor is put when its entry has one view for it (portalr ADR-0055): the
 * box its preview is drawn in, which flips to the editor and back, and the place the switch to
 * the editor goes. Without them, as on the file's page, the editor is drawn beside its controls.
 */

import { createContext } from "react";

export interface ViewSlots {
  /** The box the preview is drawn in, which the editor takes while it is open. */
  readonly viewport: HTMLElement | null;
  /** Where the switch to the editor goes, beside the preview's own views. */
  readonly toggle: HTMLElement | null;
}

export const ViewSlotsContext = createContext<ViewSlots | null>(null);
