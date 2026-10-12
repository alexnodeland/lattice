/**
 * The kit's look, pinned by screenshots (portalr ADR-0019): the frame with every component in it,
 * wide and narrow, in each scheme. Computed styles pin each component's colours and states; these
 * pin how they sit together. Baselines are Linux's, made in CI, with motion reduced and the
 * self-hosted faces loaded, so they don't move between runs.
 */

import { MessageSquare, Play, Plus, ScrollText, Zap } from "lucide-react";
import { expect, onTestFinished, test } from "vitest";
import { commands, page } from "vitest/browser";
import { render } from "vitest-browser-react";
import { AccountMenu } from "./account-menu";
import { AppShell } from "./app-shell";
import { Button } from "./button";
import { Card } from "./card";
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
          tenants={[{ id: "acme" }]}
          workspaces={[{ id: "notes" }]}
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
        <EmptyState title="No artifacts yet" action={<Button>Start a thread</Button>}>
          An artifact appears here when the agent makes one.
        </EmptyState>
      </div>
    </AppShell>
  );
}

for (const [view, width, height] of [
  ["wide", 1280, 900],
  ["narrow", 390, 844],
] as const) {
  test(`the frame and its components, ${view}`, async () => {
    await page.viewport(width, height);
    await commands.reduceMotion(true);
    onTestFinished(async () => {
      await commands.reduceMotion(false);
      await page.viewport(414, 896);
    });
    const screen = await render(<Gallery />);
    await document.fonts.ready;
    await expect(screen.container).toMatchScreenshot(`gallery-${view}-${dark ? "dark" : "light"}`, {
      screenshotOptions: { animations: "disabled" },
    });
  });
}
