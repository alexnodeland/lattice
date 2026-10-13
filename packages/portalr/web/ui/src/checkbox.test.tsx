import { useState } from "react";
import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { CheckboxGroup } from "./checkbox";

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
