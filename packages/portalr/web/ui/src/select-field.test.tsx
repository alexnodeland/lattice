import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { SelectField } from "./select-field";

test("a select field is named by its label, and submits the value chosen", async () => {
  let submitted: string | null = null;
  const screen = await render(
    <form
      onSubmit={(event) => {
        event.preventDefault();
        submitted = String(new FormData(event.currentTarget).get("role"));
      }}
    >
      <SelectField
        label="Role"
        name="role"
        options={[
          { value: "viewer", label: "Viewer" },
          { value: "editor", label: "Editor" },
        ]}
      />
      <button type="submit">Share</button>
    </form>,
  );
  const role = screen.getByRole("combobox", { name: "Role" });
  await expect.element(role).toHaveValue("viewer");
  await role.selectOptions("editor");
  await screen.getByRole("button", { name: "Share" }).click();
  expect(submitted).toBe("editor");
});
