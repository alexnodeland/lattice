/**
 * A phone's tab bar and the search that takes its place (portalr ADR-0087), as the kit draws them:
 * at the window's foot, and nothing axe finds wrong in either.
 */

import { expect, test } from "vitest";
import { page } from "vitest/browser";
import { render } from "vitest-browser-react";
import { AppShell } from "./app-shell";
import { IconButton } from "./icon-button";
import { glyphs } from "./icons";
import { PaletteFrame } from "./palette-frame";
import { TrackLink, Tracks } from "./rows";
import { axeViolations } from "./test/axe";

const tabs = (
  <>
    <Tracks label="Workspace" className="flex-1">
      <TrackLink icon={glyphs.messageSquare} render={<a href="#threads" aria-current="page" />}>
        Threads
      </TrackLink>
      <TrackLink icon={glyphs.workflow} count={3} render={<a href="#proposals" />}>
        Proposals
      </TrackLink>
    </Tracks>
    <IconButton label="Search" icon={glyphs.search} />
  </>
);

test("the tab bar sits at the window's foot, named, its proposals counted, and axe finds nothing", async () => {
  await page.viewport(375, 667);
  const screen = await render(
    <AppShell
      home={<a href="#home" />}
      switcher={<span>acme</span>}
      account={<span>a</span>}
      tabs={tabs}
    >
      <h1>Threads</h1>
    </AppShell>,
  );
  const bar = document.querySelector("[data-tab-bar]") as HTMLElement;
  expect(bar.checkVisibility()).toBe(true);
  expect(Math.round(bar.getBoundingClientRect().bottom)).toBe(window.innerHeight);
  await expect
    .element(
      screen
        .getByRole("navigation", { name: "Workspace" })
        .getByRole("link", { name: "Proposals 3 waiting for you" }),
    )
    .toBeVisible();
  expect(await axeViolations(document.body)).toEqual([]);
});

test("docked, the search holds the foot where the bar was, and axe finds nothing in it", async () => {
  await page.viewport(375, 667);
  const back = { current: null };
  await render(
    <PaletteFrame open onOpenChange={() => undefined} title="Search notes" finalFocus={back} docked>
      <input aria-label="Search or go to" />
    </PaletteFrame>,
  );
  const popup = document.querySelector("[data-docked]") as HTMLElement;
  await expect
    .poll(() => Math.round(popup.getBoundingClientRect().bottom))
    .toBe(window.innerHeight);
  expect(await axeViolations(popup)).toEqual([]);
});
