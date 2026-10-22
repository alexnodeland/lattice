/**
 * Tooltips never cover a control in their own bar (the polish pass's finding: a header's "Full
 * view" tooltip over the file's Download, then a row below). A native file's header holds its
 * Download, its page and its full view; whichever is hovered, at the top of the window or partway
 * down, 1280 and 390 wide, and in the full view, the header's other controls stay where a pointer
 * finds them. And every icon button, the thumbs as well, names itself on hover and on focus.
 */

import { Download, FileText } from "lucide-react";
import { expect, onTestFinished, test } from "vitest";
import { page, userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { InlineArtifact, Messages, Thumbs } from "./chat";
import { IconButton } from "./icon-button";

/** The tooltip open now, named `name`: its popup, the innermost element that says it is open. */
function tooltip(name: string): Element | null {
  const open = [...document.querySelectorAll("[data-open]")].filter(
    (each) => each.textContent === name && each.querySelector("[data-open]") === null,
  );
  return open[0] ?? null;
}

/** The tooltip once it has settled where it goes: the same box two frames running. */
async function settled(name: string): Promise<DOMRect> {
  let last = "";
  for (let frames = 0; ; frames += 1) {
    if (frames > 300) {
      const open = [...document.querySelectorAll("[data-open]")].map(
        (each) => `${each.tagName}:${each.textContent}`,
      );
      throw new Error(`no settled tooltip "${name}"; open: ${JSON.stringify(open)}`);
    }
    await new Promise((frame) => requestAnimationFrame(frame));
    const shown = tooltip(name);
    const box = shown?.getBoundingClientRect();
    const now = box ? JSON.stringify(box) : "";
    if (box && now === last && box.width > 0) {
      return box;
    }
    last = now;
  }
}

/** Whether a pointer at the middle of `element` reaches it, or what it holds. */
function reachable(element: Element) {
  const box = element.getBoundingClientRect();
  const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
  return hit !== null && element.contains(hit);
}

function Entry({ above }: { above: number }) {
  return (
    <div style={{ paddingTop: above }}>
      <Messages>
        <InlineArtifact
          name="atlas-brief.docx"
          kind="Word document"
          open={<a href="#page">page</a>}
          actions={<IconButton label="Download" icon={Download} />}
        >
          <p>37 kB · 2 pages · version 1</p>
        </InlineArtifact>
      </Messages>
    </div>
  );
}

/** Hover each of the header's controls, and check none of its tooltips covers another. */
async function check(names: readonly string[]) {
  const header = (name: string) =>
    page.getByRole(name === "Open its page" ? "link" : "button", { name, exact: true });
  const controls = names.map((name) => header(name).element());
  for (const name of names) {
    await userEvent.hover(header(name));
    await settled(name);
    for (const other of controls) {
      const said = other.getAttribute("aria-label");
      expect(reachable(other), `${name}'s tooltip covers ${said}`).toBe(true);
    }
    await userEvent.unhover(header(name));
  }
}

for (const width of [1280, 390]) {
  for (const [where, above] of [
    ["at the top of the window", 0],
    ["partway down the page", 300],
  ] as const) {
    test(`a file's header tooltips cover none of its controls, ${where}, ${width} wide`, async () => {
      await page.viewport(width, 800);
      onTestFinished(() => page.viewport(414, 896));
      await render(<Entry above={above} />);
      window.scrollTo(0, 0);
      await check(["Download", "Open its page", "Full view"]);
    });
  }
  test(`in the full view, its header holds the way back alone, ${width} wide`, async () => {
    await page.viewport(width, 800);
    onTestFinished(() => page.viewport(414, 896));
    const screen = await render(<Entry above={0} />);
    await screen.getByRole("button", { name: "Full view" }).click();
    const full = screen.getByRole("dialog", { name: "atlas-brief.docx" });
    await expect.element(full).toBeVisible();
    expect(full.getByRole("button", { name: "Download" }).elements()).toHaveLength(0);
    expect(full.getByRole("link", { name: "Open its page" }).elements()).toHaveLength(0);
    // The pointer is still on the button it pressed, which is now the way back.
    await userEvent.unhover(full.getByRole("button", { name: "Back to the page" }));
    await check(["Back to the page"]);
  });
}

test("the thumbs name themselves on hover and on focus, as every icon button does", async () => {
  const screen = await render(
    <div className="flex gap-2 p-16">
      <Thumbs given={null} onThumbs={async () => ({ outcome: "done" })} />
      <IconButton label="Open its page" icon={FileText} />
    </div>,
  );
  const down = screen.getByRole("button", { name: "Not helpful" });
  await userEvent.hover(down);
  await settled("Not helpful");
  await userEvent.unhover(down);
  await expect.poll(() => tooltip("Not helpful")).toBeNull();
  (down.element() as HTMLElement).focus();
  await userEvent.keyboard("{Shift>}{Tab}{/Shift}");
  await settled("Helpful");
});
