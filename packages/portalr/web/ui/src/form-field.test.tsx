import { Field } from "@base-ui/react/field";
import { expect, test } from "vitest";
import { page } from "vitest/browser";
import { render } from "vitest-browser-react";
import { FormField } from "./form-field";

test("a field's control is named by its label, described by its hint, and marked by its refusal", async () => {
  const screen = await render(
    <FormField label="Name" hint="As it appears to others." error="Too short.">
      <Field.Control />
    </FormField>,
  );
  const input = screen.getByRole("textbox", { name: "Name" });
  await expect.element(input).toHaveAttribute("aria-invalid", "true");
  await expect.element(input).toHaveAccessibleDescription(/As it appears to others\./);
  await expect.element(input).toHaveAccessibleDescription(/Too short\./);
});

test("a field with no refusal and no hint says nothing under its control", async () => {
  const screen = await render(
    <FormField label="Name">
      <Field.Control />
    </FormField>,
  );
  await expect
    .element(screen.getByRole("textbox", { name: "Name" }))
    .toHaveAccessibleDescription("");
});

test("a field is no wider than 28rem, in a form as wide as the page, and fills a narrow one", async () => {
  await page.viewport(1200, 800);
  const screen = await render(
    <div style={{ width: 1100 }}>
      <FormField label="Wide">
        <Field.Control />
      </FormField>
    </div>,
  );
  const input = screen.getByRole("textbox", { name: "Wide" }).element();
  expect(input.getBoundingClientRect().width).toBeLessThanOrEqual(448);
  await page.viewport(390, 800);
  expect(input.getBoundingClientRect().width).toBeGreaterThan(300);
});

test("a control beside its label is named by it, and described by its hint and refusal", async () => {
  const screen = await render(
    <FormField label="Notify me" hint="By email." error="Choose yes or no." beside>
      <Field.Control />
    </FormField>,
  );
  const input = screen.getByRole("textbox", { name: "Notify me" });
  await expect.element(input).toHaveAccessibleDescription("By email. Choose yes or no.");
  const label = input.element().closest("label") as Element;
  expect(label.firstElementChild).toBe(input.element());
});

test("a refusal is described by its words alone: the mark before them is hidden", async () => {
  const screen = await render(
    <FormField label="Name" error="Too short.">
      <Field.Control />
    </FormField>,
  );
  await expect
    .element(screen.getByRole("textbox", { name: "Name" }))
    .toHaveAccessibleDescription("Too short.");
});
