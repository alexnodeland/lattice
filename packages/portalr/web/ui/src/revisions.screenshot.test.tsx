/**
 * An artifact's revisions, pinned by screenshots (portalr ADR-0019, ADR-0054): a mini app's, open
 * on its Changes and on its Source, a note's, and a kind's without a renderer, as JSON; wide and
 * narrow, in each scheme, and under forced colours. Baselines are Linux's, made in CI, with the
 * faces loaded.
 */

import { expect, onTestFinished, test } from "vitest";
import { commands, page, userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { markdown } from "./artifacts";
import { IntegrationsContext } from "./integrations";
import { type RevisionShown, Revisions } from "./revisions";
import { dark } from "./test/colours";
import { compare } from "./test/compare";
import { UI_RENDERERS } from "./ui-renderers";

const RENDERERS = new Map([["note", markdown()], ...UI_RENDERERS]);

const style = (accent: string) =>
  [
    "<style>",
    "  :root { color-scheme: dark; --bg: #161923; --ink: #eef0f8; }",
    "  body { margin: 0; padding: 16px; background: var(--bg); color: var(--ink); }",
    `  .cell { aspect-ratio: 1; border-radius: 12px; color: ${accent}; }`,
    "</style>",
  ].join("\n");

const html = (accent: string, extra: string[]) =>
  [
    "<!doctype html>",
    '<html lang="en">',
    "<head>",
    '<meta charset="utf-8">',
    "<title>Tic-Tac-Toe</title>",
    style(accent),
    "</head>",
    "<body>",
    "<h1>Tic-Tac-Toe</h1>",
    '<div class="board" id="board" aria-label="Tic-tac-toe board"></div>',
    '<div class="status" id="status"></div>',
    "<script>",
    '"use strict";',
    "const LINES = [[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]];",
    ...Array.from(
      { length: 40 },
      (_, at) => `function step${at}(board) { return board[${at % 9}]; }`,
    ),
    ...extra,
    "</script>",
    "</body>",
    "</html>",
  ].join("\n");

const app = (version: number, title: string, accent: string, extra: string[]): RevisionShown => ({
  version,
  kind: "app",
  data: {
    title,
    summary: `Play tic-tac-toe against the house. Your score is saved. (${title})`,
    html: html(accent, extra),
    state: { wins: version, draws: 0 },
  },
  by: "Assistant",
  at: "2026-10-20T09:00:00Z",
});

const APP: readonly RevisionShown[] = [
  app(1, "Tic-Tac-Toe", "#6c8cff", []),
  app(2, "Tic-Tac-Toe vs. the House AI", "#ff7a7a", [
    "function blunder() { return Math.random() < 0.25; }",
  ]),
];

const NOTE: readonly RevisionShown[] = [
  { version: 1, kind: "note", data: { text: "# Standup\n\nShip on **Monday**." }, by: "You" },
  {
    version: 2,
    kind: "note",
    data: { text: "# Standup\n\nShip on **Tuesday**, after review." },
    by: "Ada",
  },
];

const PLAN: readonly RevisionShown[] = [
  {
    version: 1,
    kind: "plan",
    data: { title: "Launch", notes: 'Line one\nLine "two"', steps: ["draft"] },
    by: "Assistant",
  },
  {
    version: 2,
    kind: "plan",
    data: {
      title: "Launch",
      notes: 'Line one\nLine "two"',
      steps: ["draft", "ship"],
      owner: { name: "Ada" },
    },
    by: "Assistant",
  },
];

async function shown(revisions: readonly RevisionShown[], width: number, forced = false) {
  await page.viewport(width, 1800);
  onTestFinished(() => page.viewport(414, 896));
  if (forced) {
    await commands.forcedColors(true);
    onTestFinished(() => commands.forcedColors(false));
  }
  const screen = await render(
    <IntegrationsContext value={() => false}>
      <div data-testid="revisions" className="bg-paper p-4">
        <Revisions
          id="art_1"
          revisions={revisions}
          renderers={RENDERERS}
          compare={compare}
          // A pinned "now", so "how long ago" reads the same in every run.
          now={new Date("2026-10-20T12:00:00Z")}
        />
      </div>
    </IntegrationsContext>,
  );
  // Closed until asked (portalr ADR-0085): the newest is opened, as a reader opens it.
  await userEvent.click(screen.getByRole("button", { name: /^Version/ }).first());
  await Promise.all([
    document.fonts.load('1em "Schibsted Grotesk"'),
    document.fonts.load('600 1em "Schibsted Grotesk"'),
    document.fonts.load('1em "Fragment Mono"'),
  ]);
  await document.fonts.ready;
  return screen;
}

async function matches(name: string) {
  await new Promise((settled) => requestAnimationFrame(() => requestAnimationFrame(settled)));
  await expect(page.getByTestId("revisions")).toMatchScreenshot(
    `${name}-${dark ? "dark" : "light"}`,
    { screenshotOptions: { animations: "disabled" } },
  );
}

/** The latest revision's Source, highlighted once its grammar has loaded. */
async function onSource(screen: Awaited<ReturnType<typeof shown>>) {
  await userEvent.click(screen.getByRole("tab", { name: "Source" }));
  await expect
    .poll(() => document.querySelector('[aria-label="HTML source"] code span[style]'))
    .not.toBeNull();
}

for (const [size, width] of [
  ["wide", 900],
  ["narrow", 390],
] as const) {
  test(`an app's revisions, on its changes, ${size}`, async () => {
    await shown(APP, width);
    await matches(`revisions-app-changes-${size}`);
  });

  test(`an app's revision, on its source, ${size}`, async () => {
    await onSource(await shown(APP, width));
    await matches(`revisions-app-source-${size}`);
  });

  test(`a note's revisions, ${size}`, async () => {
    await shown(NOTE, width);
    await matches(`revisions-note-${size}`);
  });
}

test("a kind's revisions as JSON, its tree in its preview", async () => {
  const screen = await shown(PLAN, 900);
  await userEvent.click(screen.getByRole("tab", { name: "Preview" }));
  await matches("revisions-json-preview");
});

test("an app's revisions under forced colours", async () => {
  await shown(APP, 900, true);
  await matches("revisions-app-forced-colours");
});
