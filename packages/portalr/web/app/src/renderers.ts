/**
 * How the app shows each artifact kind it knows (portalr ADR-0017): the template's `note`, whose
 * Markdown is in its `text`, artifactr.ui's forms, submissions, dashboards and apps (lattice
 * RFC-0005), a native file's kinds, whose manifests name a file's bytes (portalr ADR-0048), and
 * Excalidraw's diagrams, which open on the canvas (portalr ADR-0072), and relayr's rules, drawn as
 * the pipeline they run (portalr ADR-0017).
 * Any other kind shows as JSON.
 */

import { markdown, nativeFile, type Renderers, rule, UI_RENDERERS } from "@portalr/ui";
import { diagram } from "./diagram";
import { NATIVE } from "./native";

export const RENDERERS: Renderers = new Map([
  ["note", markdown()],
  ["excalidraw_diagram", diagram],
  ["rule", rule],
  ...[...NATIVE.keys()].map((kind) => [kind, nativeFile()] as const),
  ...UI_RENDERERS,
]);
