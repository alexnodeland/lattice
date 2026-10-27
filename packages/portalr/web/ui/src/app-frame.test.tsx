import { expect, onTestFinished, test, vi } from "vitest";
import { page, userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { PROXY_READY, RESOURCE_READY } from "./app-bridge";
import { AppFrame, type AppHost, AppHostContext, type ReadApp } from "./app-frame";
import type { Shown } from "./artifacts";
import { IntegrationsContext, type IsEnabled } from "./integrations";
import { isObject } from "./json";
import { START_WITHIN } from "./on-demand/apps";
import { submissionId } from "./submission-id";
import { axeViolations } from "./test/axe";

/** An origin that is not this page's, where nothing answers: the frame loads nothing. */
const APPS = "http://127.0.0.1:9";

const DICE: ReadApp = {
  title: "Dice",
  summary: "Rolls a six-sided die.",
  html: "<button>Roll</button>",
  state: { rolled: 2 },
};

const SHOWN: Shown = { id: "app_1", version: 4 };

const allOn: IsEnabled = () => true;

/** A host at `origin`, whose writes and submissions are done, and what it was asked to do. */
function hosted(origin: string | null = APPS) {
  return {
    origin,
    setState: vi.fn(async () => ({ outcome: "done" as const })),
    submit: vi.fn(async () => ({ outcome: "done" as const })),
  } satisfies AppHost;
}

/** The app's frame, once the `apps` add-on that draws it has loaded. */
async function frameIn(screen: Awaited<ReturnType<typeof shown>>) {
  const frame = screen.getByTitle("Dice: an app made by the agent");
  await expect.element(frame).toBeInTheDocument();
  return frame.element() as HTMLIFrameElement;
}

async function shown({
  host = hosted(),
  enabled = allOn,
  on = SHOWN,
}: {
  host?: AppHost | null;
  enabled?: IsEnabled;
  on?: Shown;
} = {}) {
  return render(
    <IntegrationsContext value={enabled}>
      <AppHostContext value={host}>
        <AppFrame app={DICE} shown={on} />
      </AppHostContext>
    </IntegrationsContext>,
  );
}

test("an app is labelled as the agent's, outside its frame, with its version and summary", async () => {
  const screen = await shown();
  const app = screen.getByRole("region", { name: "Dice" });
  await expect
    .element(
      app.getByText("Made by the agent. Runs sandboxed, apart from your session. Version 4."),
    )
    .toBeVisible();
  await expect.element(app.getByText("Rolls a six-sided die.")).toBeVisible();
  expect(await axeViolations(app.element())).toEqual([]);
});

test("its frame is the sandbox on the apps' origin, sandboxed and titled, and leavable", async () => {
  const screen = await shown();
  const frame = await frameIn(screen);
  expect(frame.getAttribute("sandbox")).toBe("allow-scripts allow-same-origin");
  expect(frame.getAttribute("src")).toBe(`${APPS}/?host=${encodeURIComponent(location.origin)}`);
  expect(frame.getAttribute("referrerpolicy")).toBe("no-referrer");
  expect(frame.getAttribute("allow")).toBeNull();
  const skip = screen.getByRole("link", { name: "Skip past Dice" });
  await userEvent.tab();
  await expect.element(skip).toHaveFocus();
  await userEvent.click(skip);
  await expect.element(screen.getByText("End of Dice.")).toHaveFocus();
});

test.each([
  ["archived", { on: { ...SHOWN, archived: true } }, "This app is switched off: it was archived."],
  [
    "with mini apps off",
    { enabled: (key: string) => key !== "ui:mini-apps" },
    "Not available in this workspace: mini apps are off.",
  ],
  ["with no host", { host: null }, "Apps don't run here: this deployment has no origin for them."],
  [
    "with no apps' origin",
    { host: hosted(null) },
    "Apps don't run here: this deployment has no origin for them.",
  ],
  [
    "on the portal's own origin",
    { host: hosted(location.origin) },
    "Apps don't run here: this deployment has no origin for them.",
  ],
  [
    "at an address the deployment serves no apps for",
    { host: { ...hosted(null), elsewhere: ["http://127.0.0.1:8800", "https://m.ts.net"] } },
    "Apps don't run at this address: open the portal at http://127.0.0.1:8800 or https://m.ts.net.",
  ],
] as const)(
  "%s, nothing runs, and its label and summary say what it is",
  async (_, given, said) => {
    const screen = await shown(given);
    await expect.element(screen.getByRole("status")).toHaveTextContent(said);
    await expect.element(screen.getByText("Rolls a six-sided die.")).toBeVisible();
    expect(screen.container.querySelector("iframe")).toBeNull();
  },
);

/** Say `message` to the page as the frame's sandbox, at `origin`. */
function fromFrame(frame: HTMLIFrameElement, message: unknown, origin = APPS) {
  dispatchEvent(
    new MessageEvent("message", {
      data: JSON.stringify({ jsonrpc: "2.0", ...(message as object) }),
      origin,
      source: frame.contentWindow,
    }),
  );
}

test("a submission is shown in the host's own dialog, and sent as the person once confirmed", async () => {
  const host = hosted();
  const screen = await shown({ host });
  const values = { rolled: 6 };
  fromFrame(await frameIn(screen), {
    id: 1,
    method: "tools/call",
    params: { name: "submit", arguments: { values } },
  });
  const dialog = screen.getByRole("alertdialog", { name: "Send this from Dice?" });
  await expect.element(dialog.getByText(/"rolled": 6/)).toBeVisible();
  await expect.element(dialog.getByRole("button", { name: "Don't send it" })).toBeVisible();
  await dialog.getByRole("button", { name: "Send it" }).click();
  await vi.waitFor(() => expect(host.submit).toHaveBeenCalledOnce());
  const [id, submission] = host.submit.mock.calls[0] as unknown as [string, { nonce: string }];
  expect(submission).toEqual({ app_id: "app_1", version: 4, values, nonce: submission.nonce });
  expect(id).toBe(await submissionId("app_1", { submissions: "many", nonce: submission.nonce }));
  await expect.element(dialog).not.toBeInTheDocument();
});

test("a preview's submission is refused at once: no one is asked, and nothing is sent", async () => {
  const host = hosted();
  const screen = await render(
    <IntegrationsContext value={allOn}>
      <AppHostContext value={host}>
        <AppFrame app={DICE} shown={SHOWN} preview />
      </AppHostContext>
    </IntegrationsContext>,
  );
  fromFrame(await frameIn(screen), {
    id: 1,
    method: "tools/call",
    params: { name: "submit", arguments: { values: { rolled: 6 } } },
  });
  await new Promise((settled) => setTimeout(settled, 200));
  expect(screen.getByRole("alertdialog").elements()).toHaveLength(0);
  expect(host.submit).not.toHaveBeenCalled();
});

test("a link is opened only once the person agrees to its full address", async () => {
  const opened = vi.spyOn(window, "open").mockReturnValue(null);
  const screen = await shown();
  const url = "https://example.com/a/long/path?with=query";
  fromFrame(await frameIn(screen), { id: 2, method: "ui/open-link", params: { url } });
  const dialog = screen.getByRole("alertdialog", { name: "Open this link?" });
  await expect.element(dialog.getByText(url)).toBeVisible();
  await dialog.getByRole("button", { name: "Don't open it" }).click();
  expect(opened).not.toHaveBeenCalled();
  fromFrame(await frameIn(screen), { id: 3, method: "ui/open-link", params: { url } });
  await page.getByRole("button", { name: "Open the link" }).click();
  expect(opened).toHaveBeenCalledWith(url, "_blank", "noopener,noreferrer");
  opened.mockRestore();
});

test("a message from any other window or origin opens nothing", async () => {
  const host = hosted();
  const screen = await shown({ host });
  const submit = { id: 1, method: "tools/call", params: { name: "submit", arguments: {} } };
  fromFrame(await frameIn(screen), submit, "https://evil.example");
  dispatchEvent(new MessageEvent("message", { data: JSON.stringify(submit), origin: APPS }));
  await new Promise((settled) => setTimeout(settled, 50));
  expect(screen.container.ownerDocument.querySelector('[role="alertdialog"]')).toBeNull();
});

test("the state the app sets is written as the person, and a refusal is said", async () => {
  const host = hosted();
  host.setState.mockResolvedValueOnce({
    outcome: "refused",
    result: { rejection: { type: "forbidden" } },
  } as never);
  const screen = await shown({ host });
  const patch = [{ op: "replace", path: "/rolled", value: 5 }];
  fromFrame(await frameIn(screen), {
    id: 1,
    method: "tools/call",
    params: { name: "set_state", arguments: { patch } },
  });
  await vi.waitFor(() => expect(host.setState).toHaveBeenCalledWith("app_1", 4, { rolled: 5 }));
  await expect
    .element(screen.getByText("You can't change this app, so what you do in it isn't saved."))
    .toBeVisible();
});

test("an app asks its frame's height, kept within the least and the most", async () => {
  const screen = await shown();
  const frame = await frameIn(screen);
  expect(frame.style.height).toBe("360px");
  fromFrame(frame, { method: "ui/notifications/size-changed", params: { height: 640 } });
  await vi.waitFor(() => expect(frame.style.height).toBe("640px"));
});

test("an app past its calls a minute is said to be unanswered", async () => {
  const frame = await frameIn(await shown());
  for (let id = 0; id <= 60; id += 1) {
    fromFrame(frame, { id, method: "tools/call", params: { name: "get_state" } });
  }
  await expect.element(page.getByText(/sent more than 60 messages in a minute/)).toBeVisible();
});

test("an app's full view is a modal filling the window, labelled, and Escape brings it back", async () => {
  const screen = await shown();
  const frame = await frameIn(screen);
  await screen.getByRole("button", { name: "Full view" }).click();
  const full = screen.getByRole("dialog", { name: "Dice" });
  await expect.element(full).toHaveAttribute("aria-modal", "true");
  const back = full.getByRole("button", { name: "Back to the page" });
  await expect.element(back).toHaveFocus();
  // The host's label stays outside the frame, in sight; the frame fills the rest.
  await expect.element(full.getByText(/^Made by the agent\. .* Version 4\.$/)).toBeVisible();
  await expect.element(full.getByText("Rolls a six-sided die.")).toBeVisible();
  expect(frame.getBoundingClientRect().height).toBeGreaterThan(innerHeight * 0.6);
  // The page behind it is inert while it is open.
  expect(document.querySelector("[inert]")).not.toBeNull();
  await userEvent.keyboard("{Escape}");
  await expect.element(full).not.toBeInTheDocument();
  expect(document.querySelector("[inert]")).toBeNull();
  await expect.element(screen.getByRole("button", { name: "Full view" })).toBeVisible();
  expect(await frameIn(screen)).toBe(frame);
});

test("Escape leaves a question open in the full view alone", async () => {
  const screen = await shown();
  const frame = await frameIn(screen);
  await screen.getByRole("button", { name: "Full view" }).click();
  fromFrame(frame, {
    id: 9,
    method: "tools/call",
    params: { name: "submit", arguments: { values: { rolled: 1 } } },
  });
  const asked = screen.getByRole("alertdialog", { name: "Send this from Dice?" });
  await expect.element(asked).toBeVisible();
  await userEvent.keyboard("{Escape}");
  await expect.element(asked).not.toBeInTheDocument();
  await expect.element(screen.getByRole("dialog", { name: "Dice" })).toBeVisible();
});

test("an app is shown whole, as tall as it asks, up to twice the window", async () => {
  const screen = await shown();
  const frame = await frameIn(screen);
  fromFrame(frame, { method: "ui/notifications/size-changed", params: { height: 700 } });
  await vi.waitFor(() => expect(frame.getBoundingClientRect().height).toBe(700));
  fromFrame(frame, { method: "ui/notifications/size-changed", params: { height: 2000 } });
  await vi.waitFor(() => expect(frame.style.height).toBe("2000px"));
  expect(frame.getBoundingClientRect().height).toBe(Math.min(2000, innerHeight * 2));
});

/** The frame's window as the bridge sees it, standing in for it: what it was sent, kept. */
function stoodIn() {
  const sent: unknown[] = [];
  // A window of this page's origin, so a message can come from it and its `postMessage` be kept.
  const blank = document.body.appendChild(document.createElement("iframe"));
  const window = blank.contentWindow as Window;
  window.postMessage = (message: unknown) => sent.push(message);
  onTestFinished(() => blank.remove());
  const spy = vi.spyOn(HTMLIFrameElement.prototype, "contentWindow", "get");
  spy.mockReturnValue(window);
  onTestFinished(() => spy.mockRestore());
  const given = () => sent.filter((each) => isObject(each) && each.method === RESOURCE_READY);
  return { given };
}

test("a ready never heard: the app is given once its sandbox's page loads, and once only", async () => {
  const { given } = stoodIn();
  const frame = await frameIn(await shown());
  frame.dispatchEvent(new Event("load"));
  await vi.waitFor(() => expect(given()).toHaveLength(1));
  fromFrame(frame, { method: PROXY_READY });
  frame.dispatchEvent(new Event("load"));
  await new Promise((settled) => setTimeout(settled, 50));
  expect(given()).toHaveLength(1);
});

test("an app that never reports back is said not to have started, and can be tried again", async () => {
  stoodIn();
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  onTestFinished(() => {
    vi.useRealTimers();
  });
  const screen = await shown();
  const frame = await frameIn(screen);
  frame.dispatchEvent(new Event("load"));
  const said = screen.getByText(
    `This app didn't start. Its sandbox at ${APPS} loaded, but the app in it never reported back.`,
  );
  // The frame's own load, of a page that isn't there, may come later and time it afresh.
  await vi.waitFor(() => {
    vi.advanceTimersByTime(START_WITHIN);
    expect(said.query()).not.toBeNull();
  });
  await expect.element(said).toBeVisible();
  await screen.getByRole("button", { name: "Try again" }).click();
  await expect.element(said).not.toBeInTheDocument();
  expect(await frameIn(screen)).not.toBe(frame);
});

test("an app that reports back in time is not said to have stalled", async () => {
  stoodIn();
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  onTestFinished(() => {
    vi.useRealTimers();
  });
  const screen = await shown();
  const frame = await frameIn(screen);
  frame.dispatchEvent(new Event("load"));
  fromFrame(frame, {
    method: "ui/notifications/size-changed",
    params: { height: 400, measured: true },
  });
  vi.advanceTimersByTime(START_WITHIN);
  await new Promise((settled) => queueMicrotask(() => settled(null)));
  expect(screen.container.textContent).not.toContain("didn't start");
});
