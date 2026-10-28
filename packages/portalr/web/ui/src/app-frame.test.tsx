import { expect, onTestFinished, test, vi } from "vitest";
import { page, userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import {
  APP_BOOT,
  APP_ERROR,
  APP_STARTED,
  APP_STOPPED,
  PROXY_READY,
  RESOURCE_READY,
} from "./app-bridge";
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

test("the sandbox is given the app on its ready and on its frame's load, in either order", async () => {
  // Counted as each is said: the frame's own load, of a page that isn't there, gives it too.
  const { given } = stoodIn();
  const gives = (say: () => void) => {
    const before = given().length;
    say();
    return given().length - before;
  };
  const once = await shown();
  const first = await frameIn(once);
  expect(gives(() => fromFrame(first, { method: PROXY_READY }))).toBe(1);
  expect(gives(() => first.dispatchEvent(new Event("load")))).toBe(1);
  await once.unmount();
  // A ready never heard: the load gives it; and a load whose post the frame's page dropped
  // doesn't stop a later ready giving it again.
  const second = await frameIn(await shown());
  expect(gives(() => second.dispatchEvent(new Event("load")))).toBe(1);
  expect(gives(() => fromFrame(second, { method: PROXY_READY }))).toBe(1);
  expect(given().at(-1)).toEqual({
    jsonrpc: "2.0",
    method: RESOURCE_READY,
    params: { title: "Dice", html: DICE.html },
  });
});

const DIDNT_START =
  "This app didn't start. Nothing it held is lost. Try again, or ask the agent to rebuild it.";

/** Fake time, then run it on until `shown` holds: the frame's own load may time it afresh. */
async function waited(shown: () => void) {
  await vi.waitFor(() => {
    vi.advanceTimersByTime(START_WITHIN);
    shown();
  });
}

function faked() {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  onTestFinished(() => {
    vi.useRealTimers();
  });
}

test("a sandbox that never answers is said, as is an app that never says it runs", async () => {
  stoodIn();
  faked();
  const screen = await shown();
  const said = screen.getByRole("alert");
  await waited(() => expect(said.query()?.textContent).toContain(DIDNT_START));
  expect(said.element().textContent).toContain(`Its sandbox at ${APPS} didn't answer.`);
  fromFrame(await frameIn(screen), { method: PROXY_READY });
  await waited(() =>
    expect(said.query()?.textContent).toContain(
      `Its sandbox at ${APPS} answered, but the app in it never said it runs.`,
    ),
  );
});

test("Try again makes the frame afresh, and an app that says it runs is not said to have stalled", async () => {
  stoodIn();
  faked();
  const screen = await shown();
  const frame = await frameIn(screen);
  const said = screen.getByText(DIDNT_START);
  await waited(() => expect(said.query()).not.toBeNull());
  await screen.getByRole("button", { name: "Try again" }).click();
  await expect.element(said).not.toBeInTheDocument();
  const fresh = await frameIn(screen);
  expect(fresh).not.toBe(frame);
  fromFrame(fresh, { method: APP_STARTED });
  vi.advanceTimersByTime(START_WITHIN * 3);
  await new Promise((settled) => requestAnimationFrame(settled));
  expect(said.query()).toBeNull();
});

test("a new version's HTML clears a stalled frame's card", async () => {
  stoodIn();
  faked();
  const screen = await shown();
  const said = screen.getByText(DIDNT_START);
  await waited(() => expect(said.query()).not.toBeNull());
  await screen.rerender(
    <IntegrationsContext value={allOn}>
      <AppHostContext value={hosted()}>
        <AppFrame app={{ ...DICE, html: "<button>Roll two</button>" }} shown={SHOWN} />
      </AppHostContext>
    </IntegrationsContext>,
  );
  await expect.element(said).not.toBeInTheDocument();
});

const DREW_NOTHING = "The app hasn't drawn anything yet.";

test("what an app reports went wrong is shown as plain text under it, and said in the console", async () => {
  const warned = vi.spyOn(console, "warn").mockImplementation(() => undefined);
  onTestFinished(() => warned.mockRestore());
  const screen = await shown();
  const frame = await frameIn(screen);
  fromFrame(frame, { method: APP_BOOT, params: { drawn: "something", canvases: 1 } });
  await vi.waitFor(() =>
    expect(warned).toHaveBeenCalledWith(
      expect.stringMatching(
        /^\[app-frame\] boot: drawn=something canvases=1 outer=[\d.]+x[\d.]+ container=\d+$/,
      ),
    ),
  );
  expect(screen.getByText("The app reported a problem").query()).toBeNull();
  const looked = screen.getByText("What the app reported");
  await looked.click();
  await expect.element(screen.getByText(/^boot: drawn=something canvases=1 outer=/)).toBeVisible();
  expect(screen.getByText(DREW_NOTHING, { exact: false }).query()).toBeNull();
  const message = "<b>boom</b> \u202eevil";
  fromFrame(frame, {
    method: APP_ERROR,
    params: { kind: "error", message, source: "about:srcdoc", line: 9 },
  });
  fromFrame(frame, {
    method: APP_ERROR,
    params: { kind: "policy", message: "style-src refused", blocked: "inline" },
  });
  const summary = screen.getByText("The app reported a problem");
  // Open already, from the look before: the same disclosure, now saying there is a problem.
  await expect.element(summary).toBeInTheDocument();
  const said = "error: <b>boom</b>  evil at about:srcdoc:9";
  // The latest error is the card's, above; the report lists the rest.
  await expect.element(screen.getByText("<b>boom</b>  evil", { exact: true })).toBeVisible();
  await expect.element(screen.getByText("policy: style-src refused (inline)")).toBeVisible();
  expect(screen.container.querySelector("b")).toBeNull();
  expect(warned).toHaveBeenCalledWith(`[app-frame] ${said}`);
  fromFrame(frame, { method: APP_ERROR, params: { kind: "error", message: "Script error." } });
  await expect.element(screen.getByText("This browser doesn't say which error.")).toBeVisible();
  await expect.element(screen.getByText(said)).toBeVisible();
});

test("an app said to have drawn nothing is said to, until it draws; Try again makes it afresh", async () => {
  const warned = vi.spyOn(console, "warn").mockImplementation(() => undefined);
  onTestFinished(() => warned.mockRestore());
  const screen = await shown();
  const frame = await frameIn(screen);
  const said = screen.getByText(DREW_NOTHING, { exact: false });
  fromFrame(frame, { method: APP_BOOT, params: { drawn: "not yet" } });
  await vi.waitFor(() => expect(warned).toHaveBeenCalledOnce());
  expect(said.query()).toBeNull();
  fromFrame(frame, { method: APP_BOOT, params: { drawn: "nothing" } });
  await expect.element(said).toBeVisible();
  fromFrame(frame, { method: APP_BOOT, params: { drawn: "something" } });
  await expect.element(said).not.toBeInTheDocument();
  fromFrame(frame, { method: APP_BOOT, params: { drawn: "nothing" } });
  await expect.element(said).toBeVisible();
  await screen.getByRole("button", { name: "Try again" }).click();
  await expect.element(said).not.toBeInTheDocument();
  expect(await frameIn(screen)).not.toBe(frame);
});

const STOPPED = "The app stopped after an error";
const REPORTED = "The app reported an error";
const PACMAN = "TypeError: null is not an object (evaluating 'p.dir.x')";

/** An app's frame that said `PACMAN` was thrown, with its stack, and the latest look. */
async function threw() {
  vi.spyOn(console, "warn").mockImplementation(() => undefined);
  onTestFinished(() => {
    vi.restoreAllMocks();
  });
  const screen = await shown();
  const frame = await frameIn(screen);
  fromFrame(frame, { method: APP_BOOT, params: { drawn: "something" } });
  fromFrame(frame, {
    method: APP_ERROR,
    params: {
      kind: "error",
      message: PACMAN,
      stack: "step@about:srcdoc:88:20 / loop@about:srcdoc:120:5",
    },
  });
  return { screen, frame };
}

test("an error with no word that a loop stopped is said plainly, never as stopped, and once", async () => {
  const { screen } = await threw();
  await expect
    .element(screen.getByRole("status").getByText(REPORTED, { exact: true }))
    .toBeVisible();
  expect(screen.getByText(STOPPED).query()).toBeNull();
  // The card holds the error and the look: the report under it doesn't say them again.
  expect(screen.getByText("The app reported a problem").query()).toBeNull();
  expect(screen.getByText("What the app reported").query()).toBeNull();
  expect(screen.getByText(`error: ${PACMAN}`).query()).toBeNull();
});

test("the error a loop stopped after comes with the word it stopped, though no report came before", async () => {
  vi.spyOn(console, "warn").mockImplementation(() => undefined);
  onTestFinished(() => {
    vi.restoreAllMocks();
  });
  const screen = await shown();
  const frame = await frameIn(screen);
  fromFrame(frame, {
    method: APP_STOPPED,
    params: { stopped: "yes", message: PACMAN, stack: "loop@x" },
  });
  await expect.element(screen.getByRole("alert").getByText(PACMAN, { exact: true })).toBeVisible();
  await expect.element(screen.getByText(STOPPED)).toBeVisible();
});

test("an app whose frames stopped after its error says so, with the error and its details", async () => {
  const { screen, frame } = await threw();
  fromFrame(frame, { method: APP_STOPPED, params: { stopped: "yes" } });
  const card = screen.getByRole("alert");
  await expect.element(card.getByText(STOPPED)).toBeVisible();
  await expect.element(card.getByText(PACMAN, { exact: true })).toBeVisible();
  await card.getByText("Details").click();
  await expect
    .element(card.getByText("step@about:srcdoc:88:20 / loop@about:srcdoc:120:5"))
    .toBeVisible();
  await expect.element(card.getByText(/^boot: drawn=something/)).toBeVisible();
  expect(await axeViolations(screen.container)).toEqual([]);
  // A later error, as a tap on the broken game throws, isn't the one it stopped after.
  fromFrame(frame, { method: APP_ERROR, params: { kind: "error", message: "TypeError: tapped" } });
  await expect.element(screen.getByText("error: TypeError: tapped")).toBeInTheDocument();
  await expect.element(card.getByText(PACMAN, { exact: true })).toBeVisible();
  await expect.element(screen.getByText("The app reported a problem")).toBeInTheDocument();
  // Frames came back, as after a tap that starts the game again: no longer said to be stopped.
  fromFrame(frame, { method: APP_STOPPED, params: { stopped: "no" } });
  await expect.element(screen.getByText(REPORTED, { exact: true })).toBeVisible();
  expect(screen.getByText(STOPPED).query()).toBeNull();
});

test("Copy says an error that stopped nothing was thrown, never that the app froze", async () => {
  const { screen } = await threw();
  const written = vi.fn(async (_: string) => undefined);
  vi.spyOn(navigator, "clipboard", "get").mockReturnValue({
    writeText: written,
  } as unknown as Clipboard);
  await screen.getByRole("button", { name: "Copy the error for the assistant" }).click();
  expect(written).toHaveBeenCalledWith(
    `The app threw an error: ${PACMAN}. Please find the cause and fix it.`,
  );
});

test("an error the browser doesn't name is said as such, never as its 'Script error.'", async () => {
  vi.spyOn(console, "warn").mockImplementation(() => undefined);
  onTestFinished(() => {
    vi.restoreAllMocks();
  });
  const screen = await shown();
  const frame = await frameIn(screen);
  fromFrame(frame, { method: APP_ERROR, params: { kind: "error", message: "Script error." } });
  fromFrame(frame, { method: APP_STOPPED, params: { stopped: "yes" } });
  await expect.element(screen.getByText("This browser doesn't say which error.")).toBeVisible();
});

test("Copy puts a sentence for the assistant on the clipboard, and nothing is sent", async () => {
  const { screen, frame } = await threw();
  const written = vi.fn(async (_: string) => undefined);
  vi.spyOn(navigator, "clipboard", "get").mockReturnValue({
    writeText: written,
  } as unknown as Clipboard);
  fromFrame(frame, { method: APP_STOPPED, params: { stopped: "yes" } });
  await screen.getByRole("button", { name: "Copy the error for the assistant" }).click();
  expect(written).toHaveBeenCalledWith(
    `The app froze after an error: ${PACMAN}. Please find the cause and fix it.`,
  );
  await expect.element(screen.getByText("Copied.", { exact: false })).toBeVisible();
});

test("where the page can't copy, the sentence is shown and selected to copy by hand", async () => {
  const { screen, frame } = await threw();
  vi.spyOn(navigator, "clipboard", "get").mockReturnValue(undefined as unknown as Clipboard);
  fromFrame(frame, { method: APP_STOPPED, params: { stopped: "yes" } });
  await screen.getByRole("button", { name: "Copy the error for the assistant" }).click();
  const sentence = `The app froze after an error: ${PACMAN}. Please find the cause and fix it.`;
  await expect.element(screen.getByText(sentence)).toBeVisible();
  expect(getSelection()?.toString()).toBe(sentence);
  // Selected once: a later render leaves what the person selected since alone.
  getSelection()?.removeAllRanges();
  fromFrame(frame, { method: APP_BOOT, params: { drawn: "something", canvases: 2 } });
  await new Promise((settle) => setTimeout(settle, 100));
  expect(getSelection()?.toString()).toBe("");
});

test("Reload app makes the frame afresh, and the card goes with the old one", async () => {
  const { screen, frame } = await threw();
  fromFrame(frame, { method: APP_STOPPED, params: { stopped: "yes" } });
  const reload = screen.getByRole("button", { name: "Reload app" });
  await expect.element(reload).toBeVisible();
  await reload.click();
  await expect.element(screen.getByText(STOPPED)).not.toBeInTheDocument();
  expect(await frameIn(screen)).not.toBe(frame);
});
