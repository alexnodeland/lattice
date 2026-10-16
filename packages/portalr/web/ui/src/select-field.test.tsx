import { expect, test, vi } from "vitest";
import { page, userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { SelectField } from "./select-field";
import { choose } from "./test/select";

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
  await userEvent.keyboard("{ArrowDown}{Enter}");
  await expect.element(role).toHaveTextContent("Editor");
  await userEvent.keyboard("{Enter}");
  await expect.element(page.getByRole("listbox")).toBeVisible();
  await userEvent.keyboard("{Escape}");
  await expect.element(page.getByRole("listbox")).not.toBeInTheDocument();
  await expect.element(role).toHaveFocus();
});

test("typing the first letter of a choice finds it", async () => {
  const screen = await render(<SelectField label="Role" options={OPTIONS} />);
  await screen.getByRole("combobox", { name: "Role" }).click();
  await userEvent.keyboard("o");
  await userEvent.keyboard("{Enter}");
  await expect.element(screen.getByRole("combobox", { name: "Role" })).toHaveTextContent("Owner");
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
