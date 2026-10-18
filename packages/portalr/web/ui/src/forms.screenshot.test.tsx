/**
 * Forms' look, pinned by screenshots (portalr ADR-0019, lattice RFC-0005): a form of every
 * control, with its refusals, a button that is a form of no fields, and a form the agent asks in
 * the chat, open, answered, and with forms off. Wide and narrow, in each scheme, and in colour-blind mode. Like the
 * gallery's, the baselines are Linux's, made in CI.
 */

import { expect, onTestFinished, test } from "vitest";
import { commands, page } from "vitest/browser";
import { render } from "vitest-browser-react";
import { Card } from "./card";
import { Request } from "./chat";
import { IntegrationsContext } from "./integrations";
import { SchemaForm } from "./schema-form";
import { dark } from "./test/colours";
import { ASK_LEAVE, BUTTON, LEAVE, LEAVE_UI } from "./test/forms";

const sent = async () => ({ outcome: "done" }) as const;

function Forms() {
  return (
    <div data-testid="forms" className="flex flex-col gap-6 bg-paper p-4 text-fg">
      <Card>
        <SchemaForm title="Request leave" schema={LEAVE} ui={LEAVE_UI} onSubmit={sent} />
      </Card>
      <Card>
        <SchemaForm
          title="Ready to ship?"
          schema={BUTTON}
          ui={{ submit_label: "Ship it" }}
          onSubmit={sent}
        />
      </Card>
    </div>
  );
}

function Asked({ answeredBy, off = false }: { answeredBy?: string; off?: boolean }) {
  return (
    <div data-testid="forms" className="flex flex-col gap-6 bg-paper p-4 text-fg">
      <IntegrationsContext value={(key) => !(off && key === "ui:forms")}>
        <Request
          request={{
            kind: "question",
            tool_call_id: "call_1",
            tool_name: "ask_form",
            args: { ...ASK_LEAVE },
          }}
          onAnswer={sent}
          {...(answeredBy !== undefined && { answeredBy })}
        />
      </IntegrationsContext>
    </div>
  );
}

/** Lay out what to shoot at a width, with the faces loaded and the pointer off it. */
async function shown(width: number, what: React.ReactNode, colourBlind = false) {
  await page.viewport(width, 1600);
  onTestFinished(() => page.viewport(414, 896));
  if (colourBlind) {
    document.documentElement.dataset.cvd = "";
    onTestFinished(() => {
      delete document.documentElement.dataset.cvd;
    });
  }
  const screen = await render(what);
  await Promise.all([
    document.fonts.load('1em "Schibsted Grotesk"'),
    document.fonts.load('600 1em "Schibsted Grotesk"'),
  ]);
  await document.fonts.ready;
  await commands.pointerAway();
  return screen;
}

async function matches(name: string) {
  await expect(page.getByTestId("forms")).toMatchScreenshot(`${name}-${dark ? "dark" : "light"}`, {
    screenshotOptions: { animations: "disabled" },
  });
}

test("a form of every control, and a button, wide", async () => {
  await shown(900, <Forms />);
  await matches("forms-wide");
});

test("a form of every control, and a button, narrow", async () => {
  await shown(390, <Forms />);
  await matches("forms-narrow");
});

test("a form's refusals, under their fields, with the focus on the first", async () => {
  const screen = await shown(900, <Forms />);
  await screen.getByRole("textbox", { name: /Email while away/ }).fill("alice@");
  await screen.getByRole("button", { name: "Ask for leave" }).click();
  await expect.element(screen.getByLabelText(/First day/)).toHaveFocus();
  await matches("forms-refused");
});

test("a form in colour-blind mode", async () => {
  await shown(900, <Forms />, true);
  await matches("forms-colour-blind");
});

test("the agent asks a form in the chat", async () => {
  await shown(900, <Asked />);
  await matches("forms-asked");
});

test("the agent's form, answered by another", async () => {
  await shown(900, <Asked answeredBy="Alice" />);
  await matches("forms-answered");
});

test("the agent's form, with forms off in the workspace", async () => {
  await shown(900, <Asked off />);
  await matches("forms-off");
});
