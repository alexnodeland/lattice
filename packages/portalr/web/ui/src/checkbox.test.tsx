import { Field } from "@base-ui/react/field";
import { useState } from "react";
import { expect, test } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { Checkbox, CheckboxGroup } from "./checkbox";
import { token } from "./test/colours";

function Members() {
  const [chosen, setChosen] = useState<string[]>(["user:bob"]);
  return (
    <>
      <CheckboxGroup
        legend="Members"
        choices={[
          { value: "user:bob", label: "bob (person)" },
          { value: "service_principal:ci", label: "ci (service principal)" },
        ]}
        value={chosen}
        onValueChange={setChosen}
      />
      <output>{chosen.join(",")}</output>
    </>
  );
}

test("a checkbox group is named by its legend, each box by its words, and holds what's checked", async () => {
  const screen = await render(<Members />);
  await expect.element(screen.getByRole("group", { name: "Members" })).toBeVisible();
  await expect.element(screen.getByRole("checkbox", { name: "bob (person)" })).toBeChecked();
  await screen.getByRole("checkbox", { name: "ci (service principal)" }).click();
  await expect
    .element(screen.getByRole("status"))
    .toHaveTextContent("user:bob,service_principal:ci");
});

test("a group's hint and refusal describe it, and the refusal marks it invalid", async () => {
  const screen = await render(
    <CheckboxGroup
      legend="Handed over"
      choices={[{ value: "a", label: "On-call" }]}
      value={[]}
      onValueChange={() => undefined}
      hint="Choose 1 or more."
      error="Choose at least one."
    />,
  );
  const group = screen.getByRole("group", { name: "Handed over" });
  await expect.element(group).toHaveAttribute("aria-invalid", "true");
  await expect.element(group).toHaveAccessibleDescription("Choose 1 or more. Choose at least one.");
});

test("a group without a hint or a refusal is described by nothing", async () => {
  const screen = await render(
    <CheckboxGroup legend="Members" choices={[]} value={[]} onValueChange={() => undefined} />,
  );
  const group = screen.getByRole("group", { name: "Members" });
  await expect.element(group).not.toHaveAttribute("aria-describedby");
  await expect.element(group).not.toHaveAttribute("aria-invalid");
});

test("a box on its own is named by the label around it, toggled by Space, and ringed in focus", async () => {
  const screen = await render(
    <Field.Root>
      <Field.Label>
        <Checkbox />
        Tell the team
      </Field.Label>
    </Field.Root>,
  );
  const box = screen.getByRole("checkbox", { name: "Tell the team" });
  await userEvent.tab();
  await expect.element(box).toHaveFocus();
  expect(getComputedStyle(box.element()).outlineColor).toBe(token("focus"));
  await userEvent.keyboard(" ");
  await expect.element(box).toBeChecked();
  expect(getComputedStyle(box.element()).backgroundColor).toBe(token("accent"));
});
