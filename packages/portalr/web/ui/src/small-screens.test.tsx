/**
 * Small screens and fingers (portalr ADR-0080): nothing wider than a phone at 320 and 360, a part
 * that would be scrolling inside its own box; the rules a finger gets, 44px targets and 16px
 * fields; and the safe areas kept clear by what is pinned.
 */

import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { Breadcrumbs } from "./breadcrumbs";
import { Button } from "./button";
import { Composer, Message, Messages, RunStrip } from "./chat";
import { ItemTable } from "./item-table";
import { PageHeader } from "./page-header";
import { SegmentedFilter } from "./segmented-filter";
import { viewport } from "./test/viewport";
import { TextField } from "./text-field";

const LONG = `A line without a break ${"x".repeat(120)} and a code block:\n\n\`\`\`ts\nconst ${"name".repeat(30)} = 1;\n\`\`\``;

const PEOPLE: readonly { id: string }[] = [
  { id: "someone@example.test" },
  { id: "another-very-long-name@example.test" },
];

function Page() {
  return (
    <div className="flex flex-col gap-6 p-4">
      <PageHeader
        title="A thread whose title runs on and on past the width of any phone there is"
        breadcrumbs={[{ label: "Threads", href: "#" }]}
        actions={
          <>
            <Button variant="secondary">Share…</Button>
            <Button>Something else</Button>
          </>
        }
      />
      <Breadcrumbs
        trail={[
          { label: "Workspace", href: "#" },
          { label: "A long place name", href: "#" },
        ]}
      />
      <div className="flex flex-wrap items-end gap-3">
        <TextField type="search" label="Search" className="min-w-48 flex-1" />
        <SegmentedFilter
          label="Show"
          value="all"
          onValueChange={() => {}}
          segments={[
            { value: "all", label: "All", count: 12 },
            { value: "needs", label: "Needs you", count: 3 },
            { value: "working", label: "Working", count: 1 },
          ]}
        />
      </div>
      <ItemTable<{ id: string }>
        caption="Members"
        empty={{ title: "No one", body: "Nothing." }}
        columns={[
          { key: "who", label: "Who", cell: (row) => row.id },
          { key: "kind", label: "Kind", cell: () => "person" },
          { key: "since", label: "Since", cell: () => "2026-10-20T00:00:00Z" },
          { key: "roles", label: "Roles", cell: () => "owner, editor, viewer, triager" },
        ]}
        items={PEOPLE}
        keyOf={(row) => row.id}
      />
      <Messages>
        <Message
          message={{
            id: "m1",
            seq: 1,
            actor: { kind: "agent", run_id: "run_1", thread_id: "t" },
            content: LONG,
            kind: "message",
            runId: null,
            feedback: [],
          }}
          author="Assistant"
        />
      </Messages>
      <RunStrip
        run={
          {
            id: "run_1",
            threadId: "t",
            status: "running",
            tools: {},
            text: "",
            requests: [],
            answered: [],
            started: 1,
            startedAt: "2026-10-20T00:00:00Z",
            ended: null,
            error: null,
          } as never
        }
        onStop={async () => ({ outcome: "done" })}
        now={new Date("2026-10-20T00:01:00Z")}
      />
      <Composer onSend={async () => ({ outcome: "done" })} />
    </div>
  );
}

for (const width of [320, 360]) {
  test(`at ${width}px nothing is wider than the page: what would be scrolls inside its box`, async () => {
    await viewport(width, 740);
    await render(<Page />);
    // What scrolls inside its own box may be wider than the page: its box isn't.
    const scrolls = (element: Element | null): boolean =>
      element !== null &&
      element !== document.body &&
      (/auto|scroll/.test(getComputedStyle(element).overflowX) || scrolls(element.parentElement));
    const wide = Array.from(document.body.querySelectorAll<HTMLElement>("*"))
      .filter((element) => element.getBoundingClientRect().right > window.innerWidth + 1)
      .filter((element) => !scrolls(element.parentElement))
      .map(
        (element) =>
          `${element.tagName.toLowerCase()}.${element.className.toString().slice(0, 60)}`,
      );
    expect(wide, wide.join("\n")).toEqual([]);
    // Text that overflows its box, such as a long unbroken word, widens the page without widening a box.
    const overflowing = Array.from(document.querySelectorAll<HTMLElement>("body *"))
      .filter((element) => element.scrollWidth > element.clientWidth + 1)
      // A screen reader's text is clipped to a pixel by design.
      .filter((element) => !scrolls(element) && getComputedStyle(element).overflowX !== "hidden")
      .map(
        (element) =>
          `${element.tagName.toLowerCase()}.${element.className.toString().slice(0, 50)}`,
      );
    expect(overflowing, overflowing.join("\n")).toEqual([]);

    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(window.innerWidth);
  });
}

/** The declarations of every rule under a media condition, by selector. */
function rulesUnder(condition: string): Map<string, CSSStyleDeclaration> {
  const found = new Map<string, CSSStyleDeclaration>();
  for (const sheet of Array.from(document.styleSheets)) {
    for (const rule of Array.from(sheet.cssRules)) {
      if (rule instanceof CSSMediaRule && rule.conditionText.includes(condition)) {
        for (const inner of Array.from(rule.cssRules)) {
          if (inner instanceof CSSStyleRule) {
            found.set(inner.selectorText, inner.style);
          }
        }
      }
    }
  }
  return found;
}

test("to a finger, every control is 44px or taller, admin's density included, and a field's text is 16px", () => {
  const coarse = rulesUnder("pointer: coarse");
  const roots = Array.from(coarse.entries()).find(([selector]) =>
    selector.includes('[data-density="compact"]'),
  );
  expect(roots?.[0]).toContain(":root");
  for (const token of [
    "--icon-button-size",
    "--disclosure-target",
    "--breadcrumb-target",
    "--row-height",
  ]) {
    expect(Number.parseFloat(roots?.[1].getPropertyValue(token) ?? "0")).toBeGreaterThanOrEqual(
      2.75,
    );
  }
  const controls = Array.from(coarse.entries()).find(([selector]) => selector.includes("button"));
  expect(controls?.[1].minHeight).toBe("2.75rem");
  const fields = Array.from(coarse.entries()).find(([selector]) => selector.includes("textarea"));
  expect(fields?.[1].fontSize).toBe("max(1rem, 1em)");
});

test("the composer's dock and the drawer keep a phone's safe areas clear, and the page its top and sides", () => {
  const text = Array.from(document.styleSheets)
    .flatMap((sheet) => Array.from(sheet.cssRules))
    .map((rule) => rule.cssText)
    .join("\n");
  expect(text).toMatch(/\[data-composer-dock\][^}]*safe-area-inset-bottom/);
  expect(text).toMatch(/\[data-frame-drawer\][^}]*safe-area-inset-top/);
  expect(text).toMatch(/body[^}]*safe-area-inset-left/);
});

test("a control answers a tap at once, with no flash of the browser's, and an inner scroller keeps its scroll", async () => {
  const screen = await render(
    <div className="overflow-auto" data-scroller="">
      <Button>Tap</Button>
    </div>,
  );
  const button = screen.getByRole("button", { name: "Tap" }).element();
  expect(getComputedStyle(button).touchAction).toBe("manipulation");
  expect(
    getComputedStyle(document.documentElement).getPropertyValue("-webkit-tap-highlight-color"),
  ).toMatch(/transparent|rgba\(0, 0, 0, 0\)/);
  const scroller = document.querySelector("[data-scroller]") as HTMLElement;
  expect(getComputedStyle(scroller).overscrollBehavior).toBe("contain");
});
