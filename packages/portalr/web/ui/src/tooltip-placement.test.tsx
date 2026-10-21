/**
 * Tooltips never cover a neighbouring control (the polish pass's finding: a header's "Full view"
 * tooltip over the file's Download): with an entry at the top of the window, where a tooltip
 * can't go above its button, each of the header's other controls stays where a pointer finds it.
 * And every icon button, the thumbs as well, shows its name on hover and on focus alike.
 */

import { Download, FileText } from "lucide-react";
import { expect, onTestFinished, test } from "vitest";
import { page, userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { InlineArtifact, Messages, Thumbs } from "./chat";
import { IconButton } from "./icon-button";

/** Whether a pointer at the middle of `element` reaches it, or what it holds. */
function reachable(element: Element) {
  const box = element.getBoundingClientRect();
  const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
  return hit !== null && element.contains(hit);
}

for (const width of [1280, 390]) {
  test(`a header's tooltips leave its other controls in reach, ${width} wide`, async () => {
    await page.viewport(width, 800);
    onTestFinished(() => page.viewport(414, 896));
    const screen = await render(
      <Messages>
        <InlineArtifact
          name="atlas-brief.docx"
          kind="Word document"
          open={<a href="#page">page</a>}
          actions={<IconButton label="Download" icon={Download} />}
        >
          <div className="flex justify-between">
            <span>37 kB · 2 pages · version 1</span>
            <button type="button">Next to the header</button>
          </div>
        </InlineArtifact>
      </Messages>,
    );
    const controls = ["Download", "Open its page", "Full view", "Next to the header"].map((name) =>
      screen.getByRole(name === "Open its page" ? "link" : "button", { name }).element(),
    );
    for (const name of ["Download", "Open its page", "Full view"]) {
      const role = name === "Open its page" ? "link" : "button";
      await userEvent.hover(screen.getByRole(role, { name }));
      await expect.element(page.getByText(name, { exact: true }).last()).toBeVisible();
      for (const other of controls) {
        expect(
          reachable(other),
          `${name}'s tooltip covers ${other.textContent || other.getAttribute("aria-label")}`,
        ).toBe(true);
      }
    }
  });
}

test("the thumbs show their names on hover and on focus, as every icon button does", async () => {
  const screen = await render(
    <div className="flex gap-2 p-16">
      <Thumbs given={null} onThumbs={async () => ({ outcome: "done" })} />
      <IconButton label="Open its page" icon={FileText} />
    </div>,
  );
  await userEvent.hover(screen.getByRole("button", { name: "Not helpful" }));
  await expect.element(page.getByText("Not helpful", { exact: true }).last()).toBeVisible();
  await userEvent.unhover(screen.getByRole("button", { name: "Not helpful" }));
  (screen.getByRole("button", { name: "Helpful" }).element() as HTMLElement).focus();
  await userEvent.keyboard("{Shift>}{Tab}{/Shift}{Tab}");
  await expect.element(page.getByText("Helpful", { exact: true }).last()).toBeVisible();
});
