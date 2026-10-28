/**
 * A choice list in a sheet (portalr ADR-0087): a named radio group, each option named by its name
 * and described by its line, a finger's size, and nothing axe finds wrong, chosen or read-only.
 */

import { expect, test } from "vitest";
import { page } from "vitest/browser";
import { render } from "vitest-browser-react";
import { ChoiceList } from "./choice-list";
import { Dialog } from "./dialog";
import { axeViolations } from "./test/axe";

const OPTIONS = [
  { value: "edit", label: "Auto", line: "The assistant makes changes itself." },
  { value: "suggest", label: "Ask", line: "The assistant proposes changes for you to accept." },
] as const;

for (const disabled of [false, true]) {
  test(`a choice list in a sheet${disabled ? ", read-only," : ""} is a named radio group axe finds nothing wrong in`, async () => {
    await page.viewport(375, 667);
    const screen = await render(
      <Dialog
        open
        onOpenChange={() => undefined}
        title="Agent mode"
        {...(disabled && { description: "Fixed for this turn" })}
      >
        <ChoiceList
          label="Agent mode"
          value="edit"
          options={OPTIONS}
          disabled={disabled}
          onChange={() => undefined}
        />
      </Dialog>,
    );
    const group = screen.getByRole("radiogroup", { name: "Agent mode" });
    await expect.element(group.getByRole("radio", { name: "Auto" })).toBeChecked();
    for (const radio of group.getByRole("radio").elements()) {
      expect(radio.getBoundingClientRect().height).toBeGreaterThanOrEqual(44);
    }
    expect(await axeViolations(screen.getByRole("dialog").element())).toEqual([]);
  });
}
