import { expect, test } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { contrast, token } from "./test/colours";
import { TextField } from "./text-field";

test("a text field is named by its label, and takes what is typed", async () => {
  const screen = await render(<TextField label="Email" type="email" />);
  const input = screen.getByRole("textbox", { name: "Email" });
  await input.fill("alice@acme.test");
  await expect.element(input).toHaveValue("alice@acme.test");
});

test("its text reads on the surface", async () => {
  const screen = await render(<TextField label="Name" defaultValue="alice" />);
  const style = getComputedStyle(screen.getByRole("textbox", { name: "Name" }).element());
  expect(style.backgroundColor).toBe(token("surface"));
  expect(contrast(style.color, style.backgroundColor)).toBeGreaterThanOrEqual(4.5);
});

test("a field reached by the keyboard shows the focus ring", async () => {
  const screen = await render(<TextField label="Password" type="password" />);
  await userEvent.tab();
  const input = screen.getByLabelText("Password").element();
  expect(input.matches(":focus-visible")).toBe(true);
  expect(getComputedStyle(input).outlineColor).toBe(token("focus"));
});

test("a caller's classes go on the field, around its label", async () => {
  const screen = await render(<TextField label="Tenant" className="w-64" />);
  const field = screen.getByLabelText("Tenant").element().parentElement;
  expect(field?.classList).toContain("w-64");
  expect(field?.classList).toContain("flex");
});

test("a refused field is marked invalid, and says why beneath it", async () => {
  const screen = await render(<TextField label="Password" error="Invalid login credentials" />);
  const input = screen.getByLabelText("Password");
  await expect.element(input).toHaveAttribute("aria-invalid", "true");
  await expect.element(input).toHaveAccessibleDescription("Invalid login credentials");
});

test("a field that wasn't refused says nothing more", async () => {
  const screen = await render(<TextField label="Email" />);
  await expect.element(screen.getByLabelText("Email")).not.toHaveAttribute("aria-invalid");
});
