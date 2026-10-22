/**
 * Dashboards' look, pinned by screenshots (portalr ADR-0019, ADR-0036, lattice RFC-0005): a
 * dashboard of every panel, figures, a bar chart, a line, a donut past its inks, a table, a note
 * and a form, wide and narrow, in each scheme, in colour-blind mode, and with dashboards off. Like the charts', the
 * baselines are Linux's, made in CI, with the faces loaded and the drawings settled.
 */

import { expect, onTestFinished, test } from "vitest";
import { commands, page } from "vitest/browser";
import { render } from "vitest-browser-react";
import { DashboardView } from "./dashboard-view";
import { IntegrationsContext } from "./integrations";
import { SchemaForm } from "./schema-form";
import { dark } from "./test/colours";
import { SUPPORT } from "./test/dashboards";

function Dashboard({ off = false }: { off?: boolean }) {
  return (
    <div data-testid="dashboard" className="bg-paper p-4 text-fg">
      <IntegrationsContext value={(key) => !(off && key === "ui:dashboards")}>
        <DashboardView
          dashboard={SUPPORT}
          form={() => (
            <SchemaForm
              title="Seen the figures?"
              schema={{ type: "object" }}
              ui={{ submit_label: "Mark as read" }}
              onSubmit={async () => ({ outcome: "done" })}
            />
          )}
        />
      </IntegrationsContext>
    </div>
  );
}

/** The dashboard laid out at a width, with the faces loaded and the charts' labels measured. */
async function shown(width: number, colourBlind = false, off = false) {
  await page.viewport(width, 3200);
  onTestFinished(() => page.viewport(414, 896));
  if (colourBlind) {
    document.documentElement.dataset.cvd = "";
    onTestFinished(() => {
      delete document.documentElement.dataset.cvd;
    });
  }
  await render(<Dashboard off={off} />);
  await commands.pointerAway();
  await Promise.all([
    document.fonts.load('1em "Schibsted Grotesk"'),
    document.fonts.load('600 1em "Schibsted Grotesk"'),
  ]);
  await document.fonts.ready;
  // The bar chart names its series at their last bars once its labels are measured; with
  // dashboards off, there is no chart, and its figures are open.
  await expect
    .poll(() =>
      off
        ? document.querySelectorAll('[aria-expanded="true"]').length === 3
        : [...document.querySelectorAll("svg text")].some((t) => t.textContent === "Phone"),
    )
    .toBe(true);
  await new Promise((settled) => requestAnimationFrame(() => requestAnimationFrame(settled)));
}

async function matches(name: string) {
  await expect(page.getByTestId("dashboard")).toMatchScreenshot(
    `${name}-${dark ? "dark" : "light"}`,
    { screenshotOptions: { animations: "disabled" } },
  );
}

test("a dashboard of every panel, wide", async () => {
  await shown(1000);
  await matches("dashboard-wide");
});

test("a dashboard of every panel, narrow", async () => {
  await shown(390);
  await matches("dashboard-narrow");
});

test("a dashboard in colour-blind mode", async () => {
  await shown(1000, true);
  await matches("dashboard-colour-blind");
});

test("a dashboard with dashboards off: its figures, and no chart", async () => {
  await shown(1000, false, true);
  await matches("dashboard-off");
});
