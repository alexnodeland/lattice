/** A workspace's integrations in every state the list shows, for its tests and its screenshots. */

import type { IntegrationRow } from "../integration-list";

const ALICE = { by: "alice@acme.test", at: "2026-10-16T09:30:00Z" };

export const ROWS: readonly IntegrationRow[] = [
  {
    key: "ui:forms",
    name: "Forms",
    description: "The agent asks with a form, and people fill it in the chat.",
    on: true,
    source: "default",
    changed: null,
  },
  {
    key: "markdown:mermaid",
    name: "Mermaid",
    description: "Diagrams written as text in messages, drawn.",
    on: true,
    source: "inherited",
    changed: null,
  },
  {
    key: "ui:mini-apps",
    name: "Mini apps",
    description: "Small apps the agent writes, run apart from the portal.",
    on: true,
    source: "set",
    changed: ALICE,
  },
  {
    key: "excalidraw",
    name: "Diagrams",
    description: "Excalidraw drawings that people and agents draw on together.",
    on: false,
    source: "tenant-off",
    changed: null,
  },
  {
    key: "tracker:plane",
    name: "Plane",
    description: "Rules file and change work items in a Plane project.",
    on: false,
    source: "not-installed",
    changed: null,
  },
  {
    key: "markdown:math",
    name: "Math",
    description: "Formulas in messages and documents, typeset.",
    on: false,
    source: "set",
    changed: ALICE,
  },
  {
    key: "ui:dashboards",
    name: "Dashboards",
    description: "The agent shows figures and charts as a dashboard in the chat.",
    on: true,
    source: "set",
    changed: ALICE,
  },
];

/** The integrations whose change is in flight: one off, and one on. */
export const SAVING: ReadonlySet<string> = new Set(["markdown:math", "ui:dashboards"]);

/** The tenant's own: an off set there, the ceiling every workspace is under, and a default. */
export const TENANT_ROWS: readonly IntegrationRow[] = [
  {
    key: "excalidraw",
    name: "Diagrams",
    description: "Excalidraw drawings that people and agents draw on together.",
    on: false,
    source: "set",
    changed: ALICE,
  },
  {
    key: "ui:forms",
    name: "Forms",
    description: "The agent asks with a form, and people fill it in the chat.",
    on: true,
    source: "default",
    changed: null,
  },
];
