/**
 * How the app shows each artifact kind it knows (portalr ADR-0017): the template's `note`, whose
 * Markdown is in its `text`, and artifactr.ui's forms, submissions, dashboards and apps (lattice
 * RFC-0005). Any other kind shows as JSON.
 */

import { markdown, type Renderers, UI_RENDERERS } from "@portalr/ui";

export const RENDERERS: Renderers = new Map([["note", markdown()], ...UI_RENDERERS]);
