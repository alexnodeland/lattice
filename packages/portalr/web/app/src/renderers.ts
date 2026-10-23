/**
 * How the app shows each artifact kind it knows (portalr ADR-0017): the template's `note`, whose
 * Markdown is in its `text`, artifactr.ui's forms, submissions, dashboards and apps (lattice
 * RFC-0005), and a native file's kinds, whose manifests name a file's bytes (portalr ADR-0048).
 * Any other kind shows as JSON.
 */

import { markdown, nativeFile, type Renderers, UI_RENDERERS } from "@portalr/ui";
import { NATIVE } from "./native";

export const RENDERERS: Renderers = new Map([
  ["note", markdown()],
  ...[...NATIVE.keys()].map((kind) => [kind, nativeFile()] as const),
  ...UI_RENDERERS,
]);
