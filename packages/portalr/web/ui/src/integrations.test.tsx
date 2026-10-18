import type { IntegrationKey } from "@portalr/client";
import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import REGISTRY from "../../../schemas/integrations.json";
import { byDefault, IntegrationsContext, offSaid, useOff } from "./integrations";

function Off({ keys }: { keys: readonly IntegrationKey[] }) {
  return <p>{useOff(keys) ?? "all on"}</p>;
}

test("where no page says, each integration is as lattice's registry has it by default", () => {
  for (const known of REGISTRY) {
    expect([known.key, byDefault(known.key as IntegrationKey)]).toEqual([known.key, known.default]);
  }
});

test("by default every one of ui's integrations is on but mini apps", async () => {
  const screen = await render(<Off keys={["ui:forms", "ui:dashboards", "markdown:math"]} />);
  await expect.element(screen.getByText("all on")).toBeVisible();
  await screen.rerender(<Off keys={["ui:forms", "ui:mini-apps"]} />);
  await expect.element(screen.getByText("ui:mini-apps", { exact: true })).toBeVisible();
});

test("a page's answer says which are on, and the first off is named", async () => {
  const screen = await render(
    <IntegrationsContext value={(key) => key !== "ui:dashboards"}>
      <Off keys={["ui:forms", "ui:dashboards"]} />
    </IntegrationsContext>,
  );
  await expect.element(screen.getByText("ui:dashboards", { exact: true })).toBeVisible();
});

test("an integration that is off is said of the workspace, by name where it is ui's", () => {
  expect(offSaid("ui:forms")).toBe("Not available in this workspace: forms are off.");
  expect(offSaid("ui:mini-apps")).toBe("Not available in this workspace: mini apps are off.");
  expect(offSaid("excalidraw")).toBe("Not available in this workspace.");
});
