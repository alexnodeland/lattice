/**
 * The form controls' look, pinned by screenshots (portalr ADR-0019, ADR-0037): the select closed
 * and open, fields with a hint and a refusal, a segmented filter, every button variant and size,
 * disabled too, a row with its quiet actions, and a dialog whose way out isn't "Cancel". Wide and
 * narrow, in each scheme. Like the gallery's, the baselines are Linux's, made in CI.
 */

import { expect, onTestFinished, test } from "vitest";
import { commands, page } from "vitest/browser";
import { render } from "vitest-browser-react";
import { Button, type ButtonVariant } from "./button";
import { Card } from "./card";
import { ConfirmDialog } from "./confirm-dialog";
import { SegmentedFilter } from "./segmented-filter";
import { SelectField } from "./select-field";
import { dark } from "./test/colours";
import { TextField } from "./text-field";

const VARIANTS: readonly ButtonVariant[] = [
  "primary",
  "secondary",
  "ghost",
  "danger",
  "danger-soft",
];
const ROLES = [
  { value: "", label: "Choose a role…" },
  { value: "viewer", label: "viewer" },
  { value: "editor", label: "editor" },
  { value: "owner", label: "owner" },
];

function Controls() {
  return (
    <div data-testid="controls" className="flex flex-col gap-6 bg-paper p-4 text-fg">
      <Card className="flex flex-col gap-3">
        <SegmentedFilter
          label="Window"
          showLabel
          hint="Whole days, in UTC."
          segments={[
            { value: "7", label: "7 days" },
            { value: "30", label: "30 days" },
            { value: "90", label: "90 days" },
          ]}
          value="30"
          onValueChange={() => undefined}
        />
        <SelectField label="Role" options={ROLES} hint="What they may do." defaultValue="editor" />
        <SelectField label="To" options={ROLES} disabled />
        <TextField
          label="Workspace"
          hint="A name from the list, or your own."
          defaultValue="notes"
        />
        <TextField label="Email" error="That isn't an email address." defaultValue="alice@" />
      </Card>
      <Card className="flex flex-col gap-3">
        {(["md", "sm"] as const).map((size) => (
          <div key={size} className="flex flex-wrap items-center gap-2">
            {VARIANTS.map((variant) => (
              <Button key={variant} variant={variant} size={size}>
                {variant}
              </Button>
            ))}
            <Button size={size} disabled>
              disabled
            </Button>
            <Button size={size} variant="secondary" disabled>
              disabled
            </Button>
          </div>
        ))}
      </Card>
      <Card className="flex flex-wrap items-center justify-between gap-2">
        <span>
          portalr:triage <span className="text-muted">run_dead</span>
        </span>
        <span className="flex gap-1">
          <ConfirmDialog
            label="Retry"
            about="run run_dead"
            look="ghost"
            size="sm"
            calm
            title="Retry?"
            confirm="Retry run"
            onConfirm={async () => undefined}
          >
            It runs again.
          </ConfirmDialog>
          <ConfirmDialog
            label="Skip"
            about="run run_dead"
            look="ghost"
            size="sm"
            title="Skip?"
            confirm="Skip run"
            onConfirm={async () => undefined}
          >
            It is given up on.
          </ConfirmDialog>
          <ConfirmDialog
            label="Cancel"
            about="run run_dead"
            look="danger-soft"
            size="sm"
            dismiss="Keep running"
            title="Cancel this run?"
            confirm="Cancel run"
            onConfirm={async () => undefined}
          >
            It is stopped.
          </ConfirmDialog>
        </span>
      </Card>
    </div>
  );
}

async function shown(width: number) {
  await page.viewport(width, 1400);
  onTestFinished(() => page.viewport(414, 896));
  const screen = await render(<Controls />);
  await Promise.all([
    document.fonts.load('1em "Schibsted Grotesk"'),
    document.fonts.load('600 1em "Schibsted Grotesk"'),
  ]);
  await document.fonts.ready;
  await commands.pointerAway();
  return screen;
}

async function matches(name: string, target = page.getByTestId("controls")) {
  await expect(target).toMatchScreenshot(`${name}-${dark ? "dark" : "light"}`, {
    screenshotOptions: { animations: "disabled" },
  });
}

test("the controls, wide", async () => {
  await shown(900);
  await matches("controls-wide");
});

test("the controls, narrow", async () => {
  await shown(390);
  await matches("controls-narrow");
});

test("a select, open, with the choice marked", async () => {
  const screen = await shown(900);
  await screen.getByRole("combobox", { name: "Role" }).click();
  await expect.element(page.getByRole("listbox")).toBeVisible();
  await matches("controls-select-open", page.elementLocator(document.body));
});

test("the dialog whose way out is Keep running", async () => {
  const screen = await shown(900);
  await screen.getByRole("button", { name: "Cancel run run_dead" }).click();
  await expect.element(screen.getByRole("alertdialog", { name: "Cancel this run?" })).toBeVisible();
  await matches("controls-dialog", page.elementLocator(document.body));
});
