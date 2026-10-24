import { expect, onTestFinished, test, vi } from "vitest";
import { page, userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { IntegrationList } from "./integration-list";
import { axeViolations } from "./test/axe";
import { ROWS, SAVING, TENANT_ROWS } from "./test/integrations";

/** The list, wide, so it is a table, with spies for what it hands its caller. */
async function shown(saving: ReadonlySet<string> = new Set(), width = 1024) {
  await page.viewport(width, 900);
  onTestFinished(() => page.viewport(414, 896));
  const onSwitch = vi.fn();
  const onInherit = vi.fn();
  const screen = await render(
    <IntegrationList
      caption="Integrations in notes"
      level="workspace"
      rows={ROWS}
      saving={saving}
      onSwitch={onSwitch}
      onInherit={onInherit}
      history={(row) => <a href={`#${row.key}`}>History</a>}
    />,
  );
  return { screen, onSwitch, onInherit };
}

test("each integration's switch is named by it, and described by its state in words", async () => {
  const { screen } = await shown();
  const table = screen.getByRole("table", { name: "Integrations in notes" });
  await expect.element(table.getByRole("switch", { name: "Forms" })).toBeChecked();
  await expect
    .element(table.getByRole("switch", { name: "Forms" }))
    .toHaveAccessibleDescription("On Default");
  await expect
    .element(table.getByRole("switch", { name: "Mermaid" }))
    .toHaveAccessibleDescription("On Inherited from the tenant");
  await expect
    .element(table.getByRole("switch", { name: "Mini apps" }))
    .toHaveAccessibleDescription("On Set here");
  await expect
    .element(table.getByRole("row", { name: "Mini apps" }).getByText("alice@acme.test"))
    .toBeVisible(); // Its state is in words beside its switch, with no badge to say it twice.
  expect(table.element().querySelectorAll("[data-badge]")).toHaveLength(0);
});

test("a switch under a ceiling is off and disabled, with the reason beside it", async () => {
  const { screen, onSwitch } = await shown();
  const tenantOff = screen.getByRole("switch", { name: "Diagrams" });
  await expect.element(tenantOff).not.toBeChecked();
  await expect.element(tenantOff).toBeDisabled();
  await expect
    .element(tenantOff)
    .toHaveAccessibleDescription(
      "Off Off for the tenant The tenant turned it off, so no workspace can turn it on.",
    );
  const notInstalled = screen.getByRole("switch", { name: "Plane" });
  await expect.element(notInstalled).toBeDisabled();
  await expect
    .element(notInstalled)
    .toHaveAccessibleDescription(
      "Off Not installed in this deployment This deployment doesn't install it, so it is off everywhere.",
    );
  await tenantOff.click({ force: true });
  expect(onSwitch).not.toHaveBeenCalled();
});

test("a switch turned by keyboard hands its new state over, and Back to inherited its key", async () => {
  const { screen, onSwitch, onInherit } = await shown();
  const forms = screen.getByRole("switch", { name: "Forms" });
  // From the table's scrolling region, the next stop is the first switch.
  (screen.getByRole("region", { name: "Integrations in notes" }).element() as HTMLElement).focus();
  await userEvent.tab();
  await expect.element(forms).toHaveFocus();
  await userEvent.keyboard(" ");
  expect(onSwitch).toHaveBeenCalledWith("ui:forms", false);
  await screen.getByRole("button", { name: "Back to inherited for Mini apps" }).click();
  expect(onInherit).toHaveBeenCalledWith("ui:mini-apps");
  // Only a level's own setting goes back: the rest have none to undo.
  await expect
    .element(screen.getByRole("button", { name: "Back to inherited for Forms" }))
    .not.toBeInTheDocument();
});

test("those saving are disabled, on or off, and say so, and the others can still be turned", async () => {
  const { screen } = await shown(SAVING);
  const math = screen.getByRole("switch", { name: "Math" });
  await expect.element(math).toBeDisabled();
  await expect.element(math).not.toBeChecked();
  await expect.element(math).toHaveAccessibleDescription("Saving… Set here");
  const dashboards = screen.getByRole("switch", { name: "Dashboards" });
  await expect.element(dashboards).toBeDisabled();
  await expect.element(dashboards).toBeChecked();
  await expect
    .element(screen.getByRole("button", { name: "Back to inherited for Math" }))
    .toBeDisabled();
  await expect.element(screen.getByRole("switch", { name: "Forms" })).toBeEnabled();
});

test("on the tenant, a setting goes back to the default", async () => {
  await page.viewport(1024, 900);
  onTestFinished(() => page.viewport(414, 896));
  const screen = await render(
    <IntegrationList
      caption="Integrations on the tenant"
      level="tenant"
      rows={ROWS}
      saving={new Set()}
      onSwitch={() => undefined}
      onInherit={() => undefined}
    />,
  );
  await expect
    .element(screen.getByRole("button", { name: "Back to the default for Mini apps" }))
    .toBeVisible();
});

test("on a phone each integration is a card, its switch still named and described", async () => {
  const { screen } = await shown(new Set(), 390);
  const list = screen.getByRole("list", { name: "Integrations in notes" });
  await expect.element(list.getByRole("listitem", { name: "Mermaid" })).toBeVisible();
  await expect
    .element(list.getByRole("switch", { name: "Mermaid" }))
    .toHaveAccessibleDescription("On Inherited from the tenant");
});

test.each([
  ["wide", 1024],
  ["narrow", 390],
])("every state, %s, has nothing axe finds wrong", async (_name, width) => {
  const { screen } = await shown(SAVING, width);
  await expect.element(screen.getByText("Math").first()).toBeInTheDocument();
  expect(await axeViolations(screen.container)).toEqual([]);
});

test("on the tenant, its own off says it is the ceiling every workspace is under", async () => {
  await page.viewport(1024, 900);
  onTestFinished(() => page.viewport(414, 896));
  const screen = await render(
    <IntegrationList
      caption="Integrations on the tenant"
      level="tenant"
      rows={TENANT_ROWS}
      saving={new Set()}
      onSwitch={() => undefined}
      onInherit={() => undefined}
    />,
  );
  const diagrams = screen.getByRole("switch", { name: "Diagrams" });
  await expect.element(diagrams).toBeEnabled();
  await expect
    .element(diagrams)
    .toHaveAccessibleDescription("Off Set here Off in every workspace; none can turn it on.");
  await expect
    .element(screen.getByRole("switch", { name: "Forms" }))
    .toHaveAccessibleDescription("On Default");
});
