import { expect, test } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { contrast, token } from "./test/colours";
import { TextArea } from "./text-area";

test("a text area is named by its label, takes lines, and is four lines tall unless said", async () => {
  const screen = await render(<TextArea label="Notes" />);
  const area = screen.getByRole("textbox", { name: "Notes" });
  await area.fill("One\nTwo");
  await expect.element(area).toHaveValue("One\nTwo");
  expect(area.element().getAttribute("rows")).toBe("4");
  const taller = await render(<TextArea label="Story" rows={8} />);
  expect(taller.getByRole("textbox", { name: "Story" }).element().getAttribute("rows")).toBe("8");
});

test("its text reads on the surface, and its edge is a control's", async () => {
  const screen = await render(<TextArea label="Notes" defaultValue="Hello" />);
  const style = getComputedStyle(screen.getByRole("textbox", { name: "Notes" }).element());
  expect(style.backgroundColor).toBe(token("surface"));
  expect(style.borderTopColor).toBe(token("edge"));
  expect(contrast(style.color, style.backgroundColor)).toBeGreaterThanOrEqual(4.5);
});

test("reached by the keyboard, it shows the focus ring", async () => {
  const screen = await render(<TextArea label="Notes" />);
  await userEvent.tab();
  const area = screen.getByRole("textbox", { name: "Notes" }).element();
  expect(area.matches(":focus-visible")).toBe(true);
  expect(getComputedStyle(area).outlineColor).toBe(token("focus"));
});

test("a hint and a refusal describe it, and the refusal marks it invalid", async () => {
  const screen = await render(
    <TextArea label="Notes" hint="For the team." error="Use 500 characters or fewer." />,
  );
  const area = screen.getByRole("textbox", { name: "Notes" });
  await expect.element(area).toHaveAttribute("aria-invalid", "true");
  await expect.element(area).toHaveAccessibleDescription(/For the team\./);
  await expect.element(area).toHaveAccessibleDescription(/Use 500 characters or fewer\./);
});

test("disabled, it can't be typed in, and keeps its words readable", async () => {
  const screen = await render(<TextArea label="Notes" defaultValue="Kept" disabled />);
  const area = screen.getByRole("textbox", { name: "Notes" });
  await expect.element(area).toBeDisabled();
  const style = getComputedStyle(area.element());
  expect(contrast(style.color, style.backgroundColor)).toBeGreaterThanOrEqual(4.5);
});
