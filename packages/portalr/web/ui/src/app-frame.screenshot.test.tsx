/**
 * A mini app's chrome, pinned by screenshots (portalr ADR-0051): its label and summary where it
 * doesn't run, archived and with mini apps off, wide and narrow, in each scheme, in colour-blind
 * mode, and under forced colours; and the dialog a submission is confirmed in. The frame running
 * isn't pinned: what it shows is the app's, or Chromium's own page where nothing answers. Like the
 * gallery's, the baselines are Linux's, made in CI.
 */

import { expect, onTestFinished, test } from "vitest";
import { commands, page } from "vitest/browser";
import { render } from "vitest-browser-react";
import { AppFrame, type AppHost, AppHostContext, type ReadApp } from "./app-frame";
import { IntegrationsContext } from "./integrations";
import { dark } from "./test/colours";

const TIP: ReadApp = {
  title: "Tip splitter",
  summary: "Splits a bill between the people at the table, with the tip they choose.",
  html: "<p>0</p>",
  state: {},
};

const HOST: AppHost = {
  origin: "http://127.0.0.1:9",
  setState: async () => ({ outcome: "done" }),
  submit: async () => ({ outcome: "done" }),
};

function Gallery() {
  return (
    <div data-testid="apps" className="flex flex-col gap-8 bg-paper p-4 text-fg">
      <AppFrame app={TIP} shown={{ id: "app_1", version: 3, archived: true }} />
      <IntegrationsContext value={(key) => key !== "ui:mini-apps"}>
        <AppFrame app={{ ...TIP, title: "Dice" }} shown={{ id: "app_2", version: 1 }} />
      </IntegrationsContext>
    </div>
  );
}

/** Lay out at a width, with the faces loaded, in a mode if one is given. */
async function laidOut(width: number, mode?: "colour-blind" | "forced-colours") {
  await page.viewport(width, 1600);
  onTestFinished(() => page.viewport(414, 896));
  if (mode === "colour-blind") {
    document.documentElement.dataset.cvd = "";
    onTestFinished(() => {
      delete document.documentElement.dataset.cvd;
    });
  }
  if (mode === "forced-colours") {
    await commands.forcedColors(true);
    onTestFinished(() => commands.forcedColors(false));
  }
}

async function faces() {
  await Promise.all([
    document.fonts.load('1em "Schibsted Grotesk"'),
    document.fonts.load('600 1em "Schibsted Grotesk"'),
    document.fonts.load('1em "Fragment Mono"'),
  ]);
  await document.fonts.ready;
  await commands.pointerAway();
}

async function matches(name: string, locator = page.getByTestId("apps")) {
  await expect(locator).toMatchScreenshot(`${name}-${dark ? "dark" : "light"}`, {
    screenshotOptions: { animations: "disabled" },
  });
}

test("apps that don't run, wide", async () => {
  await laidOut(900);
  await render(<Gallery />);
  await faces();
  await matches("apps-wide");
});

test("apps that don't run, narrow", async () => {
  await laidOut(390);
  await render(<Gallery />);
  await faces();
  await matches("apps-narrow");
});

test("apps that don't run, in colour-blind mode", async () => {
  await laidOut(900, "colour-blind");
  await render(<Gallery />);
  await faces();
  await matches("apps-colour-blind");
});

test("apps that don't run, under forced colours", async () => {
  await laidOut(900, "forced-colours");
  await render(<Gallery />);
  await faces();
  await matches("apps-forced-colours");
});

test("a submission an app asks for, confirmed in the host's dialog", async () => {
  await laidOut(900);
  const screen = await render(
    <IntegrationsContext value={() => true}>
      <AppHostContext value={HOST}>
        <AppFrame app={TIP} shown={{ id: "app_1", version: 3 }} />
      </AppHostContext>
    </IntegrationsContext>,
  );
  const frame = screen.getByTitle("Tip splitter: an app made by the agent").element();
  dispatchEvent(
    new MessageEvent("message", {
      origin: HOST.origin ?? "",
      source: (frame as HTMLIFrameElement).contentWindow,
      data: JSON.stringify({
        jsonrpc: "2.0",
        id: 1,
        method: "tools/call",
        params: { name: "submit", arguments: { values: { people: 4, tip: 12.5, each: 31.25 } } },
      }),
    }),
  );
  const dialog = page.getByRole("alertdialog", { name: "Send this from Tip splitter?" });
  await expect.element(dialog).toBeVisible();
  await faces();
  await matches("app-submission", dialog);
});
