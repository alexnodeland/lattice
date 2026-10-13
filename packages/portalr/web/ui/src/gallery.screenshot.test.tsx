/**
 * The kit's look, pinned by screenshots (portalr ADR-0019): the frame with every component in it,
 * wide and narrow, in each scheme. Computed styles pin each component's colours and states; these
 * pin how they sit together, and the menu, the drawer and a dialog open. Baselines are Linux's, made in CI, with motion reduced and the
 * self-hosted faces loaded, so they don't move between runs.
 */

import { MessageSquare, Play, Plus, ScrollText, Zap } from "lucide-react";
import { expect, onTestFinished, test } from "vitest";
import { page, userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { AccountMenu } from "./account-menu";
import { AppShell } from "./app-shell";
import { Button } from "./button";
import { Card } from "./card";
import { ConfirmDialog } from "./confirm-dialog";
import { Dialog } from "./dialog";
import { EmptyState } from "./empty-state";
import { Icon } from "./icon";
import { PageHeader } from "./page-header";
import { SegmentedFilter } from "./segmented-filter";
import { NavLink, SideNav } from "./side-nav";
import { StatusBadge } from "./status-badge";
import { Switcher } from "./switcher";
import { Table } from "./table";
import { dark } from "./test/colours";
import { TextField } from "./text-field";

function Gallery() {
  return (
    <AppShell
      home={<a href="#home" />}
      switcher={
        <Switcher
          tenant="acme"
          workspace="notes"
          tenants={[{ id: "acme" }, { id: "globex" }]}
          workspaces={[
            { id: "notes", detail: "4 threads" },
            { id: "support", detail: "12 threads" },
          ]}
          onTenant={() => undefined}
          onWorkspace={() => undefined}
        />
      }
      account={
        <AccountMenu
          name="Alex Nodeland"
          appearance="system"
          onAppearance={() => undefined}
          onSignOut={() => undefined}
        />
      }
      nav={
        <SideNav label="Workspace">
          <NavLink href="#threads" icon={MessageSquare} count={1}>
            Threads
          </NavLink>
          <NavLink href="#artifacts" icon={ScrollText}>
            Artifacts
          </NavLink>
          <NavLink href="#runs" icon={Play} aria-current="page">
            Runs
          </NavLink>
          <NavLink href="#rules" icon={Zap}>
            Rules
          </NavLink>
        </SideNav>
      }
    >
      <PageHeader
        title="Runs"
        meta="The agent's turns and the rules' runs, newest first"
        actions={
          <SegmentedFilter
            label="Show"
            segments={[
              { value: "all", label: "All", count: 3 },
              { value: "you", label: "Needs you", count: 1 },
            ]}
            value="all"
            onValueChange={() => undefined}
          />
        }
      />
      <div className="flex flex-col gap-6">
        <Table caption="Runs">
          <thead>
            <tr>
              <th scope="col">Status</th>
              <th scope="col">Run</th>
              <th scope="col">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>
                <StatusBadge tone="waiting">Waiting for you</StatusBadge>
              </td>
              <td>Launch plan</td>
              <td>
                <Button variant="secondary">Answer</Button>
              </td>
            </tr>
            <tr>
              <td>
                <StatusBadge tone="failed">Dead-lettered</StatusBadge>
              </td>
              <td className="font-mono">portalr:triage</td>
              <td>
                <Button>Retry</Button>
              </td>
            </tr>
            <tr>
              <td>
                <StatusBadge tone="done">Done</StatusBadge>
              </td>
              <td>Move the launch</td>
              <td>
                <Button variant="ghost" aria-pressed>
                  Helpful
                </Button>
              </td>
            </tr>
          </tbody>
        </Table>
        <Card className="flex flex-col gap-3">
          <p>The agent wants to run publish.</p>
          <TextField label="Why? (optional)" defaultValue="The ticket had no subject" />
          <span className="flex gap-2">
            <Button>
              <Icon icon={Plus} />
              Approve
            </Button>
            <Button variant="secondary">Deny</Button>
            <Button disabled>Send</Button>
          </span>
        </Card>
        <Card className="flex flex-wrap items-center gap-3">
          <StatusBadge tone="near">Near budget</StatusBadge>
          <StatusBadge tone="over">Over budget</StatusBadge>
          <ConfirmDialog
            label="Delete acme"
            title="Delete acme?"
            confirm="Delete the tenant"
            typed="acme"
            onConfirm={async () => undefined}
          >
            Its 6 workspaces, their threads, artifacts and rules, and its 14 members' access go.
          </ConfirmDialog>
        </Card>
        <EmptyState title="No artifacts yet" action={<Button>Start a thread</Button>}>
          An artifact appears here when the agent makes one.
        </EmptyState>
      </div>
    </AppShell>
  );
}

/** A dialog over the frame, as a thread's sharing opens one. */
function Sharing() {
  return (
    <Dialog
      open
      onOpenChange={() => undefined}
      title="Share the thread"
      description="Who holds a role on it."
    >
      <TextField label="Person" defaultValue="bob" />
    </Dialog>
  );
}

/** Lay the gallery out at a width, with the faces loaded before the shot (motion is reduced). */
async function shown(width: number, height: number, dialog = false) {
  await page.viewport(width, height);
  onTestFinished(() => page.viewport(414, 896));
  const screen = await render(
    <>
      <Gallery />
      {dialog && <Sharing />}
    </>,
  );
  await Promise.all([
    document.fonts.load('1em "Schibsted Grotesk"'),
    document.fonts.load('italic 1em "Schibsted Grotesk"'),
    document.fonts.load('1em "Fragment Mono"'),
  ]);
  return screen;
}

/** The whole page, so a menu or a drawer, which portals to the body, is in the shot. */
async function matches(name: string) {
  await expect(page.elementLocator(document.body)).toMatchScreenshot(
    `${name}-${dark ? "dark" : "light"}`,
    { screenshotOptions: { animations: "disabled" } },
  );
}

test("the frame and its components, wide", async () => {
  await shown(1280, 900);
  await matches("gallery-wide");
});

test("the frame and its components, narrow", async () => {
  await shown(390, 1400);
  await matches("gallery-narrow");
});

test("the switcher's menu, open, with the keyboard on an item", async () => {
  const screen = await shown(1280, 900);
  await screen.getByRole("button", { name: "Workspace: acme, notes" }).click();
  await userEvent.keyboard("{ArrowDown}");
  await matches("gallery-menu");
});

test("the drawer, open", async () => {
  const screen = await shown(390, 1400);
  await screen.getByRole("button", { name: "Menu" }).click();
  await expect.element(screen.getByRole("dialog", { name: "Navigation" })).toBeVisible();
  await matches("gallery-drawer");
});

test("a dialog, open, over the frame", async () => {
  const screen = await shown(1280, 900, true);
  await expect.element(screen.getByRole("dialog", { name: "Share the thread" })).toBeVisible();
  await matches("gallery-dialog");
});

test("a destructive action, asked first", async () => {
  const screen = await shown(1280, 900);
  await screen.getByRole("button", { name: "Delete acme" }).click();
  await screen.getByRole("textbox", { name: "Type acme to confirm" }).fill("acme");
  await matches("gallery-confirm");
});
