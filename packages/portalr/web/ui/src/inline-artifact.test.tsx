import { useState } from "react";
import { expect, test } from "vitest";
import { page, userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { json, markdown } from "./artifacts";
import { InlineArtifact, Messages } from "./chat";
import { nativeFile } from "./native-file";
import { axeViolations } from "./test/axe";
import { UI_RENDERERS } from "./ui-renderers";

/** A field whose value is the state a full view must keep. */
function Draft() {
  const [text, setText] = useState("");
  return (
    <label>
      Draft
      <input value={text} onChange={(event) => setText(event.target.value)} />
    </label>
  );
}

function InThread({ kind }: { kind?: string }) {
  return (
    <div>
      <button type="button">Before</button>
      <Messages>
        <InlineArtifact
          name="Plan"
          {...(kind !== undefined && { kind })}
          open={<a href="#plan" aria-label="the router's link" />}
        >
          <Draft />
        </InlineArtifact>
      </Messages>
    </div>
  );
}

test("an artifact of a kind is named above what it draws, with its page in reach", async () => {
  const screen = await render(<InThread kind="Note" />);
  const entry = screen.getByRole("listitem", { name: "Plan" });
  await expect.element(entry.getByText("Note", { exact: true })).toBeVisible();
  await expect.element(entry.getByText("Plan", { exact: true })).toBeVisible();
  await expect.element(entry.getByRole("link", { name: "Open its page" })).toBeVisible();
  expect(await axeViolations(screen.container)).toEqual([]);
});

test("without a kind, as an app's, it has no name above it nor a full view of its own", async () => {
  const screen = await render(<InThread />);
  expect(screen.getByRole("button", { name: "Full view" }).elements()).toHaveLength(0);
  await expect.element(screen.getByRole("textbox", { name: "Draft" })).toBeVisible();
});

test("its full view fills the window as a modal, keeps what was entered, and returns", async () => {
  const screen = await render(<InThread kind="Form" />);
  await screen.getByRole("textbox", { name: "Draft" }).fill("half an answer");
  const open = screen.getByRole("button", { name: "Full view" });
  await open.click();
  const full = screen.getByRole("dialog", { name: "Plan" });
  await expect.element(full).toHaveAttribute("aria-modal", "true");
  const back = full.getByRole("button", { name: "Back to the page" });
  await expect.poll(() => document.activeElement).toBe(back.element());
  await expect.element(full.getByRole("textbox", { name: "Draft" })).toHaveValue("half an answer");
  // The page behind it is inert.
  expect(
    screen.getByRole("button", { name: "Before" }).element().closest("[inert]"),
  ).not.toBeNull();
  await back.click();
  await expect.element(full).not.toBeInTheDocument();
  expect(document.querySelector("[inert]")).toBeNull();
  await expect
    .element(screen.getByRole("textbox", { name: "Draft" }))
    .toHaveValue("half an answer");
  await expect.poll(() => document.activeElement?.getAttribute("aria-label")).toBe("Full view");
});

test("Escape returns a full view, unless something inside took it first", async () => {
  const screen = await render(
    <Messages>
      <InlineArtifact name="Plan" kind="Note" open={null}>
        <input
          aria-label="Keeps Escape"
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              event.preventDefault();
            }
          }}
        />
      </InlineArtifact>
    </Messages>,
  );
  await screen.getByRole("button", { name: "Full view" }).click();
  await screen.getByRole("textbox", { name: "Keeps Escape" }).click();
  await userEvent.keyboard("{Escape}");
  await expect.element(screen.getByRole("dialog", { name: "Plan" })).toBeVisible();
  await screen.getByRole("button", { name: "Back to the page" }).click();
  await screen.getByRole("button", { name: "Full view" }).click();
  await userEvent.keyboard("{Escape}");
  await expect.element(screen.getByRole("dialog")).not.toBeInTheDocument();
});

test("the header's actions: Open its page, then Full view; in the full view, Back to the page alone", async () => {
  const screen = await render(<InThread kind="Note" />);
  const entry = screen.getByRole("listitem", { name: "Plan" });
  const actions = [...entry.element().querySelectorAll("a[aria-label], button[aria-label]")].map(
    (each) => each.getAttribute("aria-label"),
  );
  expect(actions).toEqual(["Open its page", "Full view"]);
  expect(entry.getByRole("link", { name: "Open its page" }).element().getAttribute("href")).toBe(
    "#plan",
  );
  await entry.getByRole("button", { name: "Full view" }).click();
  const full = screen.getByRole("dialog", { name: "Plan" });
  await expect.element(full.getByRole("button", { name: "Back to the page" })).toBeVisible();
  expect(full.getByRole("link", { name: "Open its page" }).elements()).toHaveLength(0);
});

test("in the full view, the back button's tooltip shows above it, and one Escape leaves", async () => {
  const screen = await render(<InThread kind="Note" />);
  screen.getByRole("button", { name: "Full view" }).element().focus();
  await userEvent.keyboard("{Enter}");
  const full = screen.getByRole("dialog", { name: "Plan" });
  await expect.element(full).toBeVisible();
  // The back button's tooltip shows above the full view, not under it.
  await userEvent.hover(full.getByRole("button", { name: "Back to the page" }));
  const tip = page.getByText("Back to the page", { exact: true });
  await expect.element(tip).toBeVisible();
  const box = tip.element().getBoundingClientRect();
  const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
  expect(tip.element().contains(hit)).toBe(true);
  await userEvent.keyboard("{Escape}");
  await expect.element(screen.getByRole("dialog")).not.toBeInTheDocument();
});

test("every kind the kit draws is shown in its thread; one shown as JSON isn't", () => {
  expect(markdown().inline).toBe(true);
  expect(nativeFile().inline).toBe(true);
  expect(UI_RENDERERS.map(([kind, renderer]) => [kind, renderer.inline])).toEqual([
    ["form", true],
    ["submission", true],
    ["dashboard", true],
    ["app", true],
  ]);
  expect(json.inline).toBeUndefined();
});
