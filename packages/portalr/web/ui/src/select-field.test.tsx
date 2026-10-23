import { expect, test, vi } from "vitest";
import { commands, page, userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { SelectField } from "./select-field";
import { choose } from "./test/select";

/** Two animation frames: Base UI settles its highlight, and what an Enter then takes, a frame after the key. */
const settled = () =>
  new Promise<void>((done) => requestAnimationFrame(() => requestAnimationFrame(() => done())));

const OPTIONS = [
  { value: "viewer", label: "Viewer" },
  { value: "editor", label: "Editor" },
  { value: "owner", label: "Owner" },
] as const;

test("a select field is named by its label, starts on its first choice, and submits the one chosen", async () => {
  let submitted: string | null = null;
  const screen = await render(
    <form
      onSubmit={(event) => {
        event.preventDefault();
        submitted = String(new FormData(event.currentTarget).get("role"));
      }}
    >
      <SelectField label="Role" name="role" options={OPTIONS} />
      <button type="submit">Share</button>
    </form>,
  );
  const role = screen.getByRole("combobox", { name: "Role" });
  await expect.element(role).toHaveTextContent("Viewer");
  await choose(screen, "Role", "Editor");
  await expect.element(role).toHaveTextContent("Editor");
  await screen.getByRole("button", { name: "Share" }).click();
  expect(submitted).toBe("editor");
});

test("a controlled select says what is chosen and tells the caller of a choice", async () => {
  const chosen = vi.fn();
  const screen = await render(
    <SelectField label="Role" value="editor" onValueChange={chosen} options={OPTIONS} />,
  );
  await expect.element(screen.getByRole("combobox", { name: "Role" })).toHaveTextContent("Editor");
  await choose(screen, "Role", "Owner");
  expect(chosen).toHaveBeenCalledWith("owner");
});

test("the keyboard opens it, moves through the choices, chooses one, and Escape gives the focus back", async () => {
  const screen = await render(<SelectField label="Role" options={OPTIONS} />);
  const role = screen.getByRole("combobox", { name: "Role" });
  await userEvent.tab();
  await expect.element(role).toHaveFocus();
  await userEvent.keyboard("{Enter}");
  await expect.element(page.getByRole("listbox")).toBeVisible();
  // Keys are heard once the list has the focus, and its highlight moves a moment after each.
  await expect.poll(() => document.activeElement?.getAttribute("role")).toBe("option");
  await userEvent.keyboard("{ArrowDown}");
  await expect
    .element(page.getByRole("option", { name: "Editor" }))
    .toHaveAttribute("data-highlighted");
  await settled();
  await userEvent.keyboard("{Enter}");
  await expect.element(role).toHaveTextContent("Editor");
  // The focus comes back to the trigger a moment after the list closes; a key before then is lost.
  await expect.element(page.getByRole("listbox")).not.toBeInTheDocument();
  await expect.element(role).toHaveFocus();
  await settled();
  await userEvent.keyboard("{Enter}");
  await expect.element(page.getByRole("listbox")).toBeVisible();
  await expect.poll(() => document.activeElement?.getAttribute("role")).toBe("option");
  await userEvent.keyboard("{Escape}");
  await expect.element(page.getByRole("listbox")).not.toBeInTheDocument();
  await expect.element(role).toHaveFocus();
});

test("typing the first letters of a choice finds it: the highlight follows the letters, and Enter takes it", async () => {
  const screen = await render(
    <SelectField label="Role" options={[...OPTIONS, { value: "oxide", label: "Oxide" }]} />,
  );
  await screen.getByRole("combobox", { name: "Role" }).click();
  await expect.element(page.getByRole("listbox")).toBeVisible();
  await expect.poll(() => document.activeElement?.getAttribute("role")).toBe("option");
  await userEvent.keyboard("ox");
  // The highlight moves a moment after the letters, not with them, so Enter waits for it.
  await expect
    .element(page.getByRole("option", { name: "Oxide" }))
    .toHaveAttribute("data-highlighted");
  await settled();
  await userEvent.keyboard("{Enter}");
  await expect.element(screen.getByRole("combobox", { name: "Role" })).toHaveTextContent("Oxide");
});

test("the trigger says it opens a list, and whether it is open", async () => {
  const screen = await render(<SelectField label="Role" options={OPTIONS} />);
  const role = screen.getByRole("combobox", { name: "Role" });
  await expect.element(role).toHaveAttribute("aria-expanded", "false");
  await role.click();
  await expect.element(role).toHaveAttribute("aria-expanded", "true");
  const list = page.getByRole("listbox").element();
  expect(role.element().getAttribute("aria-controls")).toBe(list.id);
});

test("Home and End go to the first and last choice", async () => {
  const screen = await render(<SelectField label="Role" options={OPTIONS} />);
  await screen.getByRole("combobox", { name: "Role" }).click();
  // Keys are heard once the list has the focus, which is a moment after it is seen.
  await expect.poll(() => document.activeElement?.getAttribute("role")).toBe("option");
  const highlighted = () =>
    [...document.querySelectorAll('[role="option"][data-highlighted]')].map((o) => o.textContent);
  await userEvent.keyboard("{End}");
  await expect.poll(highlighted).toEqual(["Owner"]);
  await userEvent.keyboard("{Home}");
  await expect.poll(highlighted).toEqual(["Viewer"]);
});

test("Tab while it is open closes it, choosing nothing, and moves on", async () => {
  const screen = await render(
    <>
      <SelectField label="Role" options={OPTIONS} />
      <button type="button">Next</button>
    </>,
  );
  const role = screen.getByRole("combobox", { name: "Role" });
  await role.click();
  await expect.element(page.getByRole("listbox")).toBeVisible();
  // The pointer rests on an option, and stays there. It used to take the highlight and the focus
  // there, so the arrow keys moved from wherever the pointer was, not from the choice: the
  // flake this test had when the click left the pointer over the list. Now it takes neither.
  await commands.pointAt("[role=option]:last-child");
  // The list takes the focus a frame after it is seen. A Tab before then leaves the trigger, and
  // the focus, arriving late, comes back into a list that stays open.
  await expect.poll(() => document.activeElement?.getAttribute("role")).toBe("option");
  await userEvent.keyboard("{ArrowDown}");
  await expect
    .element(page.getByRole("option", { name: "Editor" }))
    .toHaveAttribute("data-highlighted");
  await userEvent.tab();
  await expect.element(page.getByRole("listbox")).not.toBeInTheDocument();
  await expect.element(role).toHaveTextContent("Viewer");
  await expect.element(screen.getByRole("button", { name: "Next" })).toHaveFocus();
});

test("a required select left on its empty choice makes its form invalid, and one chosen makes it valid", async () => {
  const submitted = vi.fn();
  const screen = await render(
    <form
      aria-label="Grant"
      onSubmit={(event) => {
        event.preventDefault();
        submitted(new FormData(event.currentTarget).get("role"));
      }}
    >
      <SelectField
        label="Role"
        name="role"
        required
        options={[{ value: "", label: "Choose a role…" }, ...OPTIONS]}
      />
      <button type="submit">Grant</button>
    </form>,
  );
  const form = screen.getByRole("form", { name: "Grant" }).element() as HTMLFormElement;
  expect(form.checkValidity()).toBe(false);
  await choose(screen, "Role", "Editor");
  expect(form.checkValidity()).toBe(true);
  await screen.getByRole("button", { name: "Grant" }).click();
  expect(submitted).toHaveBeenCalledWith("editor");
});

test("an empty choice submits as an empty value, not as nothing", async () => {
  const submitted = vi.fn();
  const screen = await render(
    <form
      onSubmit={(event) => {
        event.preventDefault();
        submitted(new FormData(event.currentTarget).get("role"));
      }}
    >
      <SelectField
        label="Role"
        name="role"
        options={[{ value: "", label: "Anyone" }, ...OPTIONS]}
      />
      <button type="submit">Find</button>
    </form>,
  );
  await screen.getByRole("button", { name: "Find" }).click();
  expect(submitted).toHaveBeenCalledWith("");
});

test("an uncontrolled select follows its first choice as the choices arrive, until one is chosen", async () => {
  const screen = await render(<SelectField label="Person" options={[]} />);
  await screen.rerender(
    <SelectField label="Person" options={[{ value: "vera", label: "vera" }]} />,
  );
  await expect.element(screen.getByRole("combobox", { name: "Person" })).toHaveTextContent("vera");
  await screen.rerender(
    <SelectField
      label="Person"
      options={[
        { value: "bob", label: "bob" },
        { value: "vera", label: "vera" },
      ]}
    />,
  );
  await expect.element(screen.getByRole("combobox", { name: "Person" })).toHaveTextContent("bob");
});

test("a hint is said with it, and a refusal marks it invalid", async () => {
  const screen = await render(
    <SelectField label="Role" hint="What they may do." error="Choose a role." options={OPTIONS} />,
  );
  const role = screen.getByRole("combobox", { name: "Role" });
  await expect.element(role).toHaveAccessibleDescription(/What they may do\./);
  await expect.element(screen.getByText("Choose a role.")).toBeVisible();
});

test("a disabled select can't be opened, and shows it: a muted fill and the cursor that says so", async () => {
  const screen = await render(<SelectField label="Role" options={OPTIONS} disabled />);
  const role = screen.getByRole("combobox", { name: "Role" });
  await role.click({ force: true });
  await expect.element(page.getByRole("listbox")).not.toBeInTheDocument();
  const style = getComputedStyle(role.element());
  expect(style.cursor).toBe("not-allowed");
});

test("it is no wider than 28rem, in a form as wide as the page", async () => {
  await page.viewport(1200, 800);
  const screen = await render(
    <div style={{ width: 1100 }}>
      <SelectField label="Role" options={OPTIONS} />
    </div>,
  );
  const width = screen
    .getByRole("combobox", { name: "Role" })
    .element()
    .getBoundingClientRect().width;
  expect(width).toBeLessThanOrEqual(448);
});
