/**
 * How the app shows each artifact kind it knows (portalr ADR-0017): the template's `note`, whose
 * Markdown is in its `text`. Any other kind shows as JSON.
 */

import { markdown, type Renderers } from "@portalr/ui";

export const RENDERERS: Renderers = new Map([["note", markdown()]]);
