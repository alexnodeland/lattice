/**
 * What ADR-0039 changes, pinned by screenshots: every status badge, the alerts and what is being
 * read, a card and a dialog with their shadows, and a table in each density. Wide, in each scheme;
 * like the gallery's, the baselines are Linux's, made in CI.
 */

import { expect, onTestFinished, test } from "vitest";
import { commands, page } from "vitest/browser";
import { render } from "vitest-browser-react";
import { Alert } from "./alert";
import { AppShell } from "./app-shell";
import { Button } from "./button";
import { Card } from "./card";
import { Dialog } from "./dialog";
import { Reading } from "./skeleton";
import { StatCard } from "./stat-card";
import { StatusBadge, type Tone } from "./status-badge";
import { Table } from "./table";
import { dark } from "./test/colours";

const TONES: readonly [Tone, string][] = [
  ["working", "Running"],
  ["waiting", "Waiting for you"],
  ["done", "Succeeded"],
  ["failed", "Dead-lettered"],
  ["retrying", "Retrying"],
  ["queued", "Queued"],
  ["stopped", "Cancelled"],
  ["near", "Near budget"],
  ["over", "Over budget"],
];

function Sheet() {
  return (
    <div data-testid="sheet" className="flex flex-col gap-4 bg-paper p-4 text-fg">
      <div className="flex flex-wrap gap-2">
        {TONES.map(([tone, word]) => (
          <StatusBadge key={tone} tone={tone}>
            {word}
          </StatusBadge>
        ))}
      </div>
      <Alert tone="error">The tenant wasn't created: that name is taken.</Alert>
      <Alert tone="warn">
        These are the newest: there may be more. A shorter window finds the rest.
      </Alert>
      <Alert>Saved.</Alert>
      <Reading>Reading the workspace's runs…</Reading>
      <div className="grid grid-cols-2 gap-4">
        <StatCard
          title="Spend"
          figure="$85.00"
          badge={<StatusBadge tone="near">Near budget</StatusBadge>}
          action={<a href="#usage">Usage</a>}
        >
          of $100.00, every 30 days
        </StatCard>
        <StatCard
          title="Failed turns"
          figure="3"
          badge={<StatusBadge tone="failed">Unavailable</StatusBadge>}
        >
          agent turns in the last day, a line long enough to wrap
        </StatCard>
      </div>
      <Card>A card, raised a little.</Card>
    </div>
  );
}

function Rowed({ ui }: { ui: "app" | "admin" }) {
  return (
    <AppShell
      ui={ui}
      home={<a href="#home" />}
      switcher={<span>acme</span>}
      account={<span>alice</span>}
    >
      <div data-testid="table">
        <Table caption="Members">
          <thead>
            <tr>
              <th scope="col">Member</th>
              <th scope="col">Kind</th>
              <th scope="col">Actions</th>
            </tr>
          </thead>
          <tbody>
            {["alice", "bob", "ci-bot"].map((name) => (
              <tr key={name}>
                <th scope="row">{name}</th>
                <td>person</td>
                <td>
                  <Button variant="danger-soft" size="sm">
                    Remove
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      </div>
    </AppShell>
  );
}

async function settled() {
  await Promise.all([
    document.fonts.load('1em "Schibsted Grotesk"'),
    document.fonts.load('600 1em "Schibsted Grotesk"'),
  ]);
  await document.fonts.ready;
  await commands.pointerAway();
}

async function matches(name: string, target = page.getByTestId("sheet")) {
  await expect(target).toMatchScreenshot(`${name}-${dark ? "dark" : "light"}`, {
    screenshotOptions: { animations: "disabled" },
  });
}

test("the statuses, alerts, what is being read, and the cards", async () => {
  await page.viewport(900, 900);
  onTestFinished(() => page.viewport(414, 896));
  await render(<Sheet />);
  await settled();
  await matches("states-sheet");
});

test("a dialog, with its shadow over a blurred scrim", async () => {
  await page.viewport(900, 600);
  onTestFinished(() => page.viewport(414, 896));
  await render(
    <>
      <Sheet />
      <Dialog
        open
        onOpenChange={() => undefined}
        title="Remove bob from acme?"
        description="bob loses every role in acme."
      >
        <Button variant="danger">Remove</Button>
      </Dialog>
    </>,
  );
  await settled();
  await matches("states-dialog", page.elementLocator(document.body));
});

test("a table in admin's density", async () => {
  await page.viewport(1100, 600);
  onTestFinished(() => page.viewport(414, 896));
  await render(<Rowed ui="admin" />);
  await settled();
  await matches("states-compact", page.elementLocator(document.body));
});

test("a table in the app's density", async () => {
  await page.viewport(1100, 600);
  onTestFinished(() => page.viewport(414, 896));
  await render(<Rowed ui="app" />);
  await settled();
  await matches("states-comfortable", page.elementLocator(document.body));
});
