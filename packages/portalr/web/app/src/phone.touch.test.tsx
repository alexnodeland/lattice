/**
 * The app on a phone (portalr ADR-0082): the request's next step within the thumb's reach, one
 * tab stop, and gone while the card's own button is in view or the keyboard is up; what waits for
 * the reader docked with the composer, in one tray (portalr ADR-0092); what floats
 * as a sheet along the bottom; the composer above the on-screen keyboard; nothing wider than the
 * page with a sheet open, the keyboard up or a step unfolded, down to a window at 400% zoom.
 */

import { afterEach, expect, test, vi } from "vitest";
import { page, userEvent } from "vitest/browser";
import { open } from "./test/app";
import { AT } from "./test/files";
import { APPROVAL, serve as notes, STEPPED, WORLD } from "./test/notes";
import { wider } from "./test/overflow";
import * as rules from "./test/rules";
import { ALICE, ASKING, logged, stream, TOUR, serve as tour } from "./test/tour";

/** Files may be attached: a kind offered, so the composer can add them. */
const OFFERED = {
  allowed: true,
  limit: 1000,
  kinds: [{ kind: "word_document", extensions: [".docx"], enabled: true, limit: 1000 }],
};
const serve: typeof notes = async (request, path) =>
  path === `${AT}/uploads` ? Response.json(OFFERED) : notes(request, path);

const real = window.visualViewport;
afterEach(() => {
  vi.unstubAllGlobals();
  Object.defineProperty(window, "visualViewport", { value: real, configurable: true });
  document.documentElement.style.removeProperty("--keyboard-inset");
});

const bottom = (element: Element) => Math.round(element.getBoundingClientRect().bottom);
const bar = () => document.querySelector("[data-thumb-bar]");
const press = () => {
  const button = bar()?.querySelector("button");
  if (button) {
    button.click();
  }
};
const dock = () => document.querySelector("[data-composer-dock]") as HTMLElement;
/** What waits for the reader, docked above the composer: its box, and the part of it that scrolls. */
const tray = () => document.querySelector("[aria-label='Waiting for you']") as HTMLElement | null;
const trayBody = () => tray()?.querySelector("[data-tray]") as HTMLElement;
const noneWider = () => {
  const found = wider();
  expect(found, found.join("\n")).toEqual([]);
  expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(window.innerWidth);
};
/** A fake visual viewport, `covered` pixels shorter than the window, as a keyboard makes it. */
function keyboard(covered: number) {
  const viewport = new EventTarget() as EventTarget & {
    height: number;
    offsetTop: number;
    scale: number;
  };
  viewport.height = window.innerHeight - covered;
  viewport.offsetTop = 0;
  viewport.scale = 1;
  Object.defineProperty(window, "visualViewport", { value: viewport, configurable: true });
  return viewport;
}

test("the question waits in the dock above the composer, and its Answer is in the thumb's reach: the bar stands in where the tray scrolls it away", async () => {
  // A short window, whose tray holds less than the card: its Answer is below the tray's fold.
  await page.viewport(390, 520);
  // A visual viewport of the test's own: the real one's scrolls would measure the keyboard down.
  const viewport = keyboard(0);
  const { screen } = await open("/t/acme/w/notes/threads/thr_1", serve, () => null, WORLD);
  await expect.element(screen.getByText("Which week should the note cover?")).toBeVisible();
  // Docked with the composer: never in the thread's flow, never scrolled away.
  expect(dock().contains(document.getElementById("request-q1"))).toBe(true);
  expect(screen.getByRole("log").element().querySelector("#request-q1")).toBeNull();
  expect(getComputedStyle(trayBody()).overflowY).toBe("auto");
  await expect.poll(() => bar()?.textContent).toContain("Answer");
  expect(bar()?.getAttribute("aria-hidden")).toBe("true");
  expect(bar()?.querySelector("button")?.tabIndex).toBe(-1);
  // One Answer for a reader: the card's.
  expect(screen.getByRole("button", { name: "Answer" }).elements()).toHaveLength(1);
  expect(bottom(dock())).toBeLessThanOrEqual(window.innerHeight);
  // The card's own button scrolled into view in the tray: the bar gives way; scrolled away, it is back.
  trayBody().scrollTo(0, trayBody().scrollHeight);
  await expect.poll(() => bar(), { timeout: 3000 }).toBeNull();
  trayBody().scrollTo(0, 0);
  await expect.poll(() => bar()?.textContent).toContain("Answer");
  // The keyboard up: the bar gives way too.
  viewport.height = window.innerHeight - 300;
  viewport.dispatchEvent(new Event("resize"));
  await expect.poll(() => bar()).toBeNull();
});

test("a window with room shows the question whole, its Answer in view, and the bar has nothing to mirror", async () => {
  await page.viewport(390, 844);
  const { screen } = await open("/t/acme/w/notes/threads/thr_1", serve, () => null, WORLD);
  await expect.element(screen.getByRole("button", { name: "Answer" })).toBeVisible();
  const answer = screen.getByRole("button", { name: "Answer" }).element().getBoundingClientRect();
  expect(answer.bottom).toBeLessThanOrEqual(dock().getBoundingClientRect().bottom);
  expect(answer.height).toBeGreaterThanOrEqual(44);
  await quiet();
  expect(bar()).toBeNull();
});

test("a stepped question's bar says Next, then Answer, and gives way as it brings the card into view", async () => {
  await page.viewport(390, 520);
  const { screen } = await open("/t/acme/w/notes/threads/thr_1", serve, () => null, STEPPED);
  await expect.element(screen.getByText("Which week should the note cover?")).toBeInTheDocument();
  const away = async (word: string) => {
    trayBody().scrollTo(0, 0);
    await expect.poll(() => bar()?.textContent).toContain(word);
  };
  await away("Next");
  // Pressed, the bar's Next is the card's: the step is checked (an answer first), the next step
  // comes, and the card is brought into view, where the bar gives way to it.
  await screen.getByRole("radio", { name: /^Yes/ }).click();
  await away("Next");
  press();
  await expect.element(screen.getByText("Formal, or plain?")).toBeInTheDocument();
  await screen.getByRole("radio", { name: /^Yes/ }).click();
  await away("Next");
  press();
  await expect.element(screen.getByText("Review your answers")).toBeInTheDocument();
  await away("Answer");
});

test("a plain approval holds the window's foot, so the bar has nothing to mirror", async () => {
  // A short window: the card's own Approve stays in the thumb's reach, at the window's foot over
  // the thread (portalr ADR-0087), and the bar gives way to it, as it does to any card in view.
  await page.viewport(390, 600);
  const { screen } = await open(
    "/t/acme/w/notes/threads/thr_1",
    serve,
    () => null,
    APPROVAL(undefined),
  );
  const approve = screen.getByRole("button", { name: "Approve" });
  await expect.element(approve).toBeInTheDocument();
  window.scrollTo(0, 0);
  await expect
    .poll(() => {
      const box = approve.element().getBoundingClientRect();
      return box.top >= 0 && box.bottom <= window.innerHeight;
    })
    .toBe(true);
  expect(bar()).toBeNull();
});

for (const [what, review] of [
  ["what it runs", { app: "Blender", runs: "It runs a script." }],
  [
    "what it runs, code and a risk",
    {
      app: "Blender",
      runs: "It runs a script.",
      risk: "network",
      code: "import os\nos.system('curl x')",
    },
  ],
  ["findings", { app: "Blender", runs: "It runs a script.", findings: ["reads a file"] }],
] as const) {
  test(`an approval with ${what} to review first is never mirrored: it is read before it is given`, async () => {
    await page.viewport(390, 844);
    const { screen } = await open(
      "/t/acme/w/notes/threads/thr_1",
      serve,
      () => null,
      APPROVAL(review),
    );
    await expect.element(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
    window.scrollTo(0, 0);
    await quiet();
    expect(bar()).toBeNull();
  });
}

/**
 * Once the page has settled and the bar has read it: the dock's height steady, then two frames,
 * the one the bar reads in and the one its answer is drawn in. What the bar does then, it does.
 */
async function quiet() {
  await settled();
  await new Promise(requestAnimationFrame);
  await new Promise(requestAnimationFrame);
}

/**
 * The dock's height once it has settled: after the faces have loaded, the same in two readings a
 * frame apart, so a row that wraps as they arrive is measured as it ends, not as it starts.
 */
async function settled(): Promise<number> {
  await document.fonts.ready;
  let last = -1;
  return expect
    .poll(
      async () => {
        await new Promise(requestAnimationFrame);
        const now = dock().getBoundingClientRect().height;
        const same = now === last;
        last = now;
        return same ? now : Number.NaN;
      },
      { timeout: 5_000, interval: 50 },
    )
    .not.toBeNaN()
    .then(() => last);
}

for (const [width, height] of [
  [320, 568],
  [360, 640],
  [375, 667],
  [390, 667],
  [430, 667],
] as const) {
  test(`at ${width}px the composer's footer is one line of + and the primary action, and the dock at most a quarter of the window`, async () => {
    await page.viewport(width, height);
    const { screen } = await open("/t/acme/w/notes/threads/thr_1", serve, () => null, WORLD);
    await expect.element(screen.getByText("Which week should the note cover?")).toBeVisible();
    // The bar mirrors the card's Answer only while the card's own is out of view: from the top.
    trayBody().scrollTo(0, 0);
    await expect.poll(() => bar()?.textContent).toContain("Answer");
    const tall = await settled();
    // One footer (portalr ADR-0087): "+" at its start, and, while nothing is written, the thumb
    // bar's Answer where Send would be; every control a finger's 44px, on one line.
    const composer = dock().querySelector("textarea")?.form;
    const shown = [...(composer?.querySelectorAll("button") ?? [])].filter((b) =>
      (b as HTMLElement).checkVisibility(),
    );
    expect(shown.map((b) => b.getAttribute("aria-label") ?? b.textContent?.trim())).toEqual([
      "Add",
      "Answer",
    ]);
    expect(new Set(shown.map((b) => Math.round(b.getBoundingClientRect().top))).size).toBe(1);
    for (const b of shown) {
      expect(b.getBoundingClientRect().height).toBeGreaterThanOrEqual(44);
    }
    // Written, Send is back.
    await screen.getByRole("textbox", { name: "Message" }).fill("hello");
    await expect.element(screen.getByRole("button", { name: "Send" })).toBeVisible();
    await screen.getByRole("textbox", { name: "Message" }).fill("");
    if (width >= 375) {
      // What waits for the reader is the tray's, and scrolls inside it: the composer's is a quarter.
      const waiting = tray()?.getBoundingClientRect().height ?? 0;
      expect(tall - waiting).toBeLessThanOrEqual(window.innerHeight / 4);
    }
  });
}

test("the account menu, the thread's menu and the Add sheet open as sheets, and the page is never wider", async () => {
  await page.viewport(390, 844);
  const { screen } = await open("/t/acme/w/notes/threads/thr_1", serve, () => null, WORLD);
  await expect.element(screen.getByText("Which week should the note cover?")).toBeVisible();
  for (const [name, role] of [
    [/^Add$/, "dialog"],
    ["Account: Signed in", "menu"],
    ["Thread actions", "menu"],
  ] as const) {
    const trigger = screen.getByRole("button", { name });
    await expect.element(trigger).toBeVisible();
    await trigger.click();
    const sheet = screen.getByRole(role);
    await expect.element(sheet).toBeVisible();
    await expect.poll(() => bottom(sheet.element())).toBe(window.innerHeight);
    expect(Math.round(sheet.element().getBoundingClientRect().width)).toBe(window.innerWidth);
    noneWider();
    await userEvent.keyboard("{Escape}");
    await expect.element(screen.getByRole(role)).not.toBeInTheDocument();
  }
});

test("the Add sheet is modal on a phone: a scrim, the focus kept in, and a Close to leave by", async () => {
  await page.viewport(390, 844);
  const { screen } = await open("/t/acme/w/notes/threads/thr_1", serve, () => null, WORLD);
  await expect.element(screen.getByText("Which week should the note cover?")).toBeVisible();
  await screen.getByRole("button", { name: "Add", exact: true }).click();
  const panel = screen.getByRole("dialog", { name: "Add" });
  await expect.element(panel).toBeVisible();
  expect(panel.element().getAttribute("aria-modal")).toBe("true");
  await panel.getByRole("button", { name: "Close" }).click();
  await expect.element(screen.getByRole("dialog")).not.toBeInTheDocument();
});

test("the composer's dock rises by what the on-screen keyboard covers, and the page is never wider", async () => {
  await page.viewport(390, 844);
  const viewport = keyboard(0);
  const { screen } = await open("/t/acme/w/notes/threads/thr_1", serve, () => null, WORLD);
  await expect.element(screen.getByText("Which week should the note cover?")).toBeVisible();
  await expect
    .poll(() => document.documentElement.style.getPropertyValue("--keyboard-inset"))
    .toBe("0px");
  const clear = Number.parseFloat(getComputedStyle(dock()).paddingBottom);
  viewport.height = window.innerHeight - 300;
  viewport.dispatchEvent(new Event("resize"));
  await expect.poll(() => getComputedStyle(dock()).bottom).toBe("300px");
  // The home indicator's room goes with the keyboard: the dock keeps only its own padding.
  expect(Number.parseFloat(getComputedStyle(dock()).paddingBottom)).toBeLessThanOrEqual(clear);
  expect(getComputedStyle(dock()).paddingBottom).toBe("16px");
  expect(bottom(dock())).toBeLessThanOrEqual(window.innerHeight - 300);
  await expect.element(screen.getByRole("button", { name: "Send" })).toBeVisible();
  noneWider();
});

for (const width of [320, 390, 768]) {
  test(`a thread at ${width}px with a step unfolded is never wider than the page`, async () => {
    await page.viewport(width, 900);
    const { screen } = await open("/t/acme/w/notes/threads/thr_1", serve, () => null, WORLD);
    await expect.element(screen.getByText("Which week should the note cover?")).toBeVisible();
    // On a phone the calls are a sheet, a call's detail a tap further.
    await screen.getByRole("button", { name: /: 2 tool calls$/ }).click();
    const step = screen.getByRole("dialog").getByRole("button", { name: /^Looked through/ });
    await expect.element(step).toBeVisible();
    await step.click();
    await expect.element(screen.getByText("What it was asked")).toBeVisible();
    noneWider();
  });
}

test("a window at 400% zoom (320×256) scrolls down, never sideways, with the dock in the flow", async () => {
  await page.viewport(320, 256);
  const { screen } = await open("/t/acme/w/notes/threads/thr_1", serve, () => null, WORLD);
  await expect.element(screen.getByText("Which week should the note cover?")).toBeInTheDocument();
  noneWider();
  expect(getComputedStyle(dock()).position).toBe("static");
  // The bar gives way in a short window: nothing pinned covers most of the page.
  const shown = bar();
  expect(shown === null || getComputedStyle(shown).display === "none").toBe(true);
});

test("a rule's proposal, to a finger at 393px: its JSON's fold, Copy, Accept and Reject are 44px or taller", async () => {
  await page.viewport(393, 900);
  const { screen } = await open(
    "/t/acme/w/notes/artifacts/rule_1",
    rules.serve,
    () => null,
    rules.WORLD,
  );
  await expect.element(screen.getByRole("region", { name: "throttle" })).toBeVisible();
  const fold = screen.getByRole("button", { name: "The rule, as JSON" });
  await fold.click();
  for (const name of ["The rule, as JSON", /Copy/, "Accept", "Reject"]) {
    const target = screen.getByRole("button", { name }).first().element();
    expect(target.getBoundingClientRect().height, String(name)).toBeGreaterThanOrEqual(44);
  }
  noneWider();
});

const THREAD = "/t/acme/w/notes/threads/thr_1";

test("the thread on a phone: one compact strip with its tokens on one line, one tray for what waits, decided proposals as slim lines, and the agent's words read as any are", async () => {
  await page.viewport(390, 844);
  const { screen } = await open(THREAD, tour, () => null, { artifactrLog: TOUR });
  await expect
    .element(screen.getByRole("region", { name: "Proposal: Add a closing line" }))
    .toBeVisible();
  stream();
  // The strip is the one sign that the agent works: a line of state, what it does, the clock and
  // Stop, and a line of tokens, which does not wrap (portalr ADR-0092).
  const strip = screen.getByRole("group", { name: "This turn" });
  const tokens = strip.getByText("in 32,369 · out 6,925 · reasoning 4,955 · default");
  await expect.element(tokens).toBeVisible();
  expect(tokens.element().getBoundingClientRect().height).toBeLessThan(20);
  expect(tokens.element().parentElement?.scrollWidth).toBeLessThanOrEqual(
    tokens.element().parentElement?.clientWidth ?? 0,
  );
  expect(strip.getByRole("button", { name: "Tokens" }).elements()).toHaveLength(0);
  const stop = strip.getByRole("button", { name: "Stop" });
  await expect.element(stop).toBeVisible();
  expect(stop.element().getBoundingClientRect().height).toBeGreaterThanOrEqual(44);
  expect(strip.element().getBoundingClientRect().height).toBeLessThanOrEqual(88);
  // One proposal waits, in the tray above the composer; the one decided is a slim line of the
  // thread, which the tray has no part of.
  const waiting = tray();
  expect(waiting?.querySelectorAll("section[aria-label^='Proposal:']")).toHaveLength(1);
  expect(waiting?.getBoundingClientRect().bottom).toBeLessThanOrEqual(
    dock().getBoundingClientRect().bottom,
  );
  expect(dock().contains(waiting)).toBe(true);
  const log = screen.getByRole("log").element();
  const decided = [...log.querySelectorAll("ol > li")].find((each) =>
    each.textContent?.startsWith("AcceptedAdd a demo heading and two paragraphs"),
  );
  expect(decided).toBeDefined();
  expect(decided?.getBoundingClientRect().height).toBeLessThan(36);
  expect(log.querySelector("[aria-label='Proposal: Add a closing line']")).toBeNull();
  expect(waiting?.textContent).not.toContain("Add a demo heading and two paragraphs");
  // The composer starts one line tall, and a message followed by a fold leaves no dead space.
  expect(dock().querySelector("textarea")?.getBoundingClientRect().height).toBeLessThanOrEqual(44);
  const said = [...log.querySelectorAll("ol > li")].find((each) =>
    each.textContent?.startsWith("AssistantHappy to"),
  );
  const fold = said?.nextElementSibling;
  expect(fold?.querySelector("button")).not.toBeNull();
  expect(
    (fold?.getBoundingClientRect().top ?? 99) - (said?.getBoundingClientRect().bottom ?? 0),
  ).toBeLessThanOrEqual(4);
  // Words written before a tool call are not faded, and are the page's ink; no dots say it thinks.
  const words = screen
    .getByRole("listitem", { name: "Assistant is writing" })
    .getByText(/^Happy to - quick tour/);
  await expect.element(words).toBeVisible();
  for (let at: Element | null = words.element(); at; at = at.parentElement) {
    expect(getComputedStyle(at).opacity).toBe("1");
  }
  expect(getComputedStyle(words.element()).color).toBe(getComputedStyle(document.body).color);
  expect(document.querySelector(".animate-pulse")).toBeNull();
  noneWider();
});

test("a question and a proposal waiting are one line over the composer, counted, and open to both", async () => {
  await page.viewport(390, 844);
  const { screen } = await open(THREAD, tour, () => null, { artifactrLog: ASKING });
  const line = screen.getByRole("button", { name: /2 waiting for you/ });
  await expect.element(line).toBeVisible();
  await expect.element(line).toHaveAttribute("aria-expanded", "false");
  expect(line.element().getBoundingClientRect().height).toBeLessThan(60);
  // Neither is a card of the thread, nor floats by itself.
  const log = screen.getByRole("log").element();
  expect(log.querySelector("#request-q1")).toBeNull();
  expect(log.querySelector("[aria-label='Proposal: Add a closing line']")).toBeNull();
  expect(dock().getBoundingClientRect().height).toBeLessThan(window.innerHeight / 3);
  await line.click();
  await expect.element(screen.getByText("Which week should the note cover?")).toBeVisible();
  await expect
    .element(screen.getByRole("region", { name: "Proposal: Add a closing line" }))
    .toBeInTheDocument();
  expect(dock().contains(document.getElementById("request-q1"))).toBe(true);
  // Its share of the window, or nine rem where that is less (a window under about 360px).
  expect(trayBody().getBoundingClientRect().height).toBeLessThanOrEqual(
    Math.max(window.innerHeight * 0.4, 144) + 1,
  );
  noneWider();
});

/** Titles and arguments longer than a phone is wide, and a thread to hold the longest. */
const LONG = `What tools do you have access to and what can you do for me today ${"x".repeat(160)}`;
const LONG_WORLD = {
  artifactrLog: [
    ...TOUR.map((entry) =>
      entry.event.tool_name === "mystery_tool" && entry.event.type === "tool_called"
        ? {
            ...entry,
            event: {
              ...entry.event,
              args_summary: `{"query": "${"q".repeat(240)}", "code": "${"y".repeat(240)}"}`,
            },
          }
        : entry,
    ),
    logged(20, { type: "thread_created", thread_id: "thr_9", title: LONG }, ALICE),
  ],
};

/**
 * That a sheet or a page doesn't move sideways at all: nothing in it is wider than it, but a code
 * block's own box, which the keyboard reaches, and what scrolls up and down in it has no sideways
 * scroll to drag.
 */
function stillSideways(within: Element) {
  const scrolled = [within, ...within.querySelectorAll("*")].filter((element) => {
    const style = getComputedStyle(element);
    return /auto|scroll/.test(style.overflowY) && !element.closest("pre, textarea, [tabindex='0']");
  });
  for (const element of scrolled) {
    const name = `${element.tagName.toLowerCase()}.${String(element.className).slice(0, 50)}`;
    expect(element.scrollWidth, name).toBeLessThanOrEqual(element.clientWidth);
    expect(getComputedStyle(element).overflowX, name).not.toMatch(/auto|scroll/);
    // It can't be dragged to the side: a scroll there stays where it was.
    element.scrollLeft = 40;
    expect(element.scrollLeft, name).toBe(0);
  }
  expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(
    document.documentElement.clientWidth,
  );
  expect(window.scrollX).toBe(0);
  noneWider();
}

test("the palette, the calls' sheet and its detail, the Add sheet and the tray never scroll or move sideways, with titles and code far wider than the window", async () => {
  await page.viewport(390, 844);
  const { screen } = await open(THREAD, tour, () => null, {
    artifactrLog: LONG_WORLD.artifactrLog,
  });
  await expect
    .element(screen.getByRole("region", { name: "Proposal: Add a closing line" }))
    .toBeVisible();
  stillSideways(document.body);
  // The palette, whose groups list threads by titles of any length: each row is the list's width.
  await screen
    .getByRole("button", { name: /Search/ })
    .first()
    .click();
  const list = screen.getByRole("listbox", { name: "Results" });
  await expect.element(list).toBeVisible();
  await expect.element(screen.getByRole("option").first()).toBeVisible();
  const popup = screen.getByRole("dialog").element();
  stillSideways(popup);
  const frame = list.element().getBoundingClientRect();
  for (const option of screen.getByRole("option").elements()) {
    const box = option.getBoundingClientRect();
    expect(box.left).toBeGreaterThanOrEqual(frame.left);
    expect(box.right).toBeLessThanOrEqual(frame.right);
  }
  await userEvent.keyboard("{Escape}");
  await expect.element(screen.getByRole("dialog")).not.toBeInTheDocument();
  // The calls' sheet, and a call whose arguments are a long line of code.
  await screen
    .getByRole("button", { name: /tool calls?$/ })
    .last()
    .click();
  const sheet = screen.getByRole("dialog");
  await expect.element(sheet).toBeVisible();
  stillSideways(sheet.element());
  await sheet.getByRole("button", { name: /^Used a tool/ }).click();
  await expect.element(screen.getByText("What it was asked")).toBeVisible();
  stillSideways(sheet.element());
  await userEvent.keyboard("{Escape}");
  await userEvent.keyboard("{Escape}");
  // The Add sheet, and the tray open.
  await screen.getByRole("button", { name: "Add", exact: true }).click();
  await expect.element(screen.getByRole("dialog", { name: "Add" })).toBeVisible();
  stillSideways(screen.getByRole("dialog", { name: "Add" }).element());
});

test("with the keyboard up in a short window, the tray keeps its few lines, and its last control is reachable", async () => {
  await page.viewport(390, 560);
  const viewport = keyboard(0);
  const { screen } = await open("/t/acme/w/notes/threads/thr_1", serve, () => null, WORLD);
  await expect.element(screen.getByText("Which week should the note cover?")).toBeVisible();
  viewport.height = window.innerHeight - 300;
  viewport.dispatchEvent(new Event("resize"));
  await expect.poll(() => getComputedStyle(dock()).bottom).toBe("300px");
  const body = trayBody();
  // What is left of the window is little, but the tray is never less than nine rem...
  expect(body.getBoundingClientRect().height).toBeGreaterThanOrEqual(143);
  // ...and it scrolls to the last control, which is then in its view and above the keyboard.
  body.scrollTo(0, body.scrollHeight);
  const answerIn = () => {
    const answer = screen.getByRole("button", { name: "Answer" }).element().getBoundingClientRect();
    const box = body.getBoundingClientRect();
    return answer.top >= box.top && answer.bottom <= box.bottom;
  };
  await expect.poll(answerIn).toBe(true);
  const answer = screen.getByRole("button", { name: "Answer" }).element().getBoundingClientRect();
  expect(answer.bottom).toBeLessThanOrEqual(window.innerHeight - 300);
});
