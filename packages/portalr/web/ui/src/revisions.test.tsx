import { expect, test, vi } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { type AppHost, AppHostContext } from "./app-frame";
import { markdown } from "./artifacts";
import { IntegrationsContext, type IsEnabled } from "./integrations";
import { changedSaid, type RevisionShown, Revisions } from "./revisions";
import { axeViolations } from "./test/axe";
import { compare } from "./test/compare";
import { UI_RENDERERS } from "./ui-renderers";

const RENDERERS = new Map([["note", markdown()], ...UI_RENDERERS]);

/** An origin that is not this page's, where nothing answers: the frame loads nothing. */
const APPS = "http://127.0.0.1:9";

const host = (): AppHost => ({
  origin: APPS,
  setState: vi.fn(async () => ({ outcome: "done" as const })),
  submit: vi.fn(async () => ({ outcome: "done" as const })),
});

const page = (title: string, body: string) =>
  `<!doctype html>\n<html>\n<head>\n<title>${title}</title>\n</head>\n<body>\n${body}\n</body>\n</html>`;

const app = (version: number, title: string, body: string, at?: string): RevisionShown => ({
  version,
  kind: "app",
  data: { title, summary: `Plays ${title}.`, html: page(title, body), state: {} },
  by: "Assistant",
  ...(at && { at }),
});

const APP_REVISIONS = [
  app(1, "Dice", '<button id="roll">Roll</button>', "2026-10-01T09:00:00Z"),
  app(2, "Dice game", '<button id="roll">Roll the die</button>\n<p id="score"></p>'),
];

function shown(
  revisions: readonly RevisionShown[],
  { enabled = () => true, apps = host() }: { enabled?: IsEnabled; apps?: AppHost | null } = {},
) {
  return render(
    <IntegrationsContext value={enabled}>
      <AppHostContext value={apps}>
        <Revisions id="art_1" revisions={revisions} renderers={RENDERERS} compare={compare} />
      </AppHostContext>
    </IntegrationsContext>,
  );
}

test("newest first, the latest open and the rest closed, each saying who, when and what", async () => {
  const screen = await shown(APP_REVISIONS);
  const list = screen.getByRole("list", { name: "Revisions" });
  const latest = list.getByRole("listitem").nth(0);
  const first = list.getByRole("listitem").nth(1);
  await expect.element(latest).toHaveAccessibleName("Version 2");
  await expect.element(first).toHaveAccessibleName("Version 1");
  await expect
    .element(latest.getByRole("button", { name: /^Version 2/ }))
    .toHaveAttribute("aria-expanded", "true");
  await expect
    .element(first.getByRole("button", { name: /^Version 1/ }))
    .toHaveAttribute("aria-expanded", "false");
  await expect
    .element(latest.getByText("Changed the title, the summary and the HTML (+3 −2)"))
    .toBeVisible();
  await expect.element(first.getByText("First version")).toBeVisible();
  const when = first.getByRole("time").element();
  expect(when.getAttribute("dateTime")).toBe("2026-10-01T09:00:00Z");
  expect(when.getAttribute("title")).toBe(new Date("2026-10-01T09:00:00Z").toLocaleString());
  await expect.element(first.getByText(/by Assistant, .+ ago/)).toBeVisible();
  // Closed, a revision draws nothing but its summary.
  expect(first.getByRole("tab").elements()).toHaveLength(0);
  expect(await axeViolations(list.element())).toEqual([]);
});

test("an app's revision: its title and summary as text, then its Changes, Source and Preview", async () => {
  const screen = await shown(APP_REVISIONS);
  const latest = screen.getByRole("listitem", { name: "Version 2" });
  await expect.element(latest.getByText("Plays Dice game.")).toBeVisible();
  const tabs = latest.getByRole("tab");
  expect(tabs.elements().map((tab) => tab.textContent)).toEqual(["Preview", "Source", "Changes"]);
  await expect
    .element(latest.getByRole("tab", { name: "Changes" }))
    .toHaveAttribute("aria-selected", "true");
  // The chosen tab is underlined in the working colour; the others aren't.
  const edge = (name: string) =>
    getComputedStyle(latest.getByRole("tab", { name }).element()).borderBottomColor;
  expect(edge("Changes")).not.toBe(edge("Source"));
  // The title's words, and the HTML's lines, each said to a reader as added or removed.
  const html = latest.getByRole("region", { name: "Changes to the HTML" });
  await expect
    .element(html.getByRole("insertion").filter({ hasText: "Roll the die" }))
    .toHaveTextContent('added: <button id="roll">Roll the die</button>');
  await expect
    .element(html.getByRole("deletion").filter({ hasText: "Roll" }))
    .toHaveTextContent('removed: <button id="roll">Roll</button>');
  const title = latest.getByRole("region", { name: "title", exact: true });
  await expect.element(title.getByRole("insertion")).toHaveTextContent("added: game");
  expect(await axeViolations(latest.element())).toEqual([]);
});

test("its Source is its HTML as written, unescaped, numbered, and its state as JSON", async () => {
  const screen = await shown(APP_REVISIONS);
  const latest = screen.getByRole("listitem", { name: "Version 2" });
  await userEvent.click(latest.getByRole("tab", { name: "Source" }));
  const source = latest.getByRole("region", { name: "HTML source" });
  await expect.element(source).toBeVisible();
  expect(source.element().querySelector("pre")?.textContent).toContain(
    '<button id="roll">Roll the die</button>',
  );
  await expect.element(latest.getByRole("region", { name: "state source" })).toBeVisible();
  await expect.element(latest.getByRole("button", { name: "Copy the HTML" })).toBeVisible();
});

test("an app's preview runs on asking, one revision at a time, and saves nothing", async () => {
  const apps = host();
  const screen = await shown(APP_REVISIONS, { apps });
  const latest = screen.getByRole("listitem").nth(0);
  const first = screen.getByRole("listitem").nth(1);
  await userEvent.click(latest.getByRole("tab", { name: "Preview" }));
  // Nothing runs until asked.
  expect(screen.container.querySelector("iframe")).toBeNull();
  await userEvent.click(latest.getByRole("button", { name: "Run version 2" }));
  await expect
    .element(latest.getByTitle("Dice game: an app made by the agent"))
    .toBeInTheDocument();
  // The host's label stays; its title isn't drawn twice.
  await expect
    .element(
      latest.getByText("Made by the agent. Runs sandboxed, apart from your session. Version 2."),
    )
    .toBeVisible();
  expect(latest.getByRole("heading", { name: "Dice game" }).elements()).toHaveLength(0);
  await userEvent.click(first.element().querySelector("[aria-expanded]") as HTMLElement);
  await userEvent.click(first.getByRole("tab", { name: "Preview" }));
  await userEvent.click(first.getByRole("button", { name: "Run version 1" }));
  await expect.element(first.getByTitle("Dice: an app made by the agent")).toBeInTheDocument();
  expect(screen.container.querySelectorAll("iframe")).toHaveLength(1);
  await userEvent.click(first.getByRole("button", { name: "Stop version 1" }));
  expect(screen.container.querySelectorAll("iframe")).toHaveLength(0);
  // What a preview may send is the bridge's to refuse, before anyone is asked: app-bridge.test.ts.
  // Closed and opened again, it waits to be asked to run again.
  await userEvent.click(first.getByRole("button", { name: "Run version 1" }));
  const summary = first.element().querySelector("[aria-expanded]") as HTMLElement;
  await userEvent.click(summary);
  await userEvent.click(summary);
  await userEvent.click(first.getByRole("tab", { name: "Preview" }));
  await expect.element(first.getByRole("button", { name: "Run version 1" })).toBeVisible();
  expect(screen.container.querySelectorAll("iframe")).toHaveLength(0);
});

test("an archived app's revisions run nothing: they have no Preview", async () => {
  const screen = await render(
    <IntegrationsContext value={() => true}>
      <AppHostContext value={host()}>
        <Revisions
          id="art_1"
          revisions={APP_REVISIONS}
          renderers={RENDERERS}
          compare={compare}
          archived
        />
      </AppHostContext>
    </IntegrationsContext>,
  );
  const latest = screen.getByRole("listitem", { name: "Version 2" });
  expect(
    latest
      .getByRole("tab")
      .elements()
      .map((tab) => tab.textContent),
  ).toEqual(["Source", "Changes"]);
});

test("a part the version before had and this one hasn't is said to be removed", async () => {
  const plan = (version: number, data: Record<string, unknown>): RevisionShown => ({
    version,
    kind: "app",
    data,
    by: "Ada",
  });
  const screen = await shown([
    plan(1, { title: "Dice", summary: "Rolls.", html: "<p>1</p>" }),
    plan(2, { title: "Dice", html: "<p>1</p>" }),
  ]);
  const latest = screen.getByRole("listitem", { name: "Version 2" });
  await expect.element(latest.getByText("Changed the summary")).toBeVisible();
  await expect
    .element(latest.getByRole("region", { name: "summary", exact: true }).getByRole("deletion"))
    .toHaveTextContent("removed: Rolls.");
});

test("a time ahead of the page's clock is just now, and the moment is read, not only hovered", async () => {
  const screen = await render(
    <Revisions
      id="art_1"
      revisions={[{ ...(APP_REVISIONS[0] as RevisionShown), at: "2026-10-20T12:05:00Z" }]}
      renderers={RENDERERS}
      compare={compare}
      now={new Date("2026-10-20T12:00:00Z")}
    />,
  );
  const when = screen.getByRole("time").element();
  expect(when.textContent).toBe(`just now (${new Date("2026-10-20T12:05:00Z").toLocaleString()})`);
});

test("where apps don't run, an app's revision has no Preview", async () => {
  const screen = await shown(APP_REVISIONS, { enabled: () => false });
  const latest = screen.getByRole("listitem", { name: "Version 2" });
  expect(
    latest
      .getByRole("tab")
      .elements()
      .map((tab) => tab.textContent),
  ).toEqual(["Source", "Changes"]);
});

test("an app's first revision, where apps don't run, opens on its Source", async () => {
  const none = await shown([APP_REVISIONS[0] as RevisionShown], { apps: null });
  await expect
    .element(none.getByRole("tab", { name: "Source" }))
    .toHaveAttribute("aria-selected", "true");
});

test("a closed revision opens from the keyboard, and closes again", async () => {
  const screen = await shown(APP_REVISIONS);
  const first = screen.getByRole("listitem", { name: "Version 1" });
  const summary = first.element().querySelector("[aria-expanded]") as HTMLElement;
  summary.focus();
  await userEvent.keyboard("{Enter}");
  await expect.element(first.getByRole("tab", { name: "Preview" })).toBeVisible();
  // The first version has nothing before it to compare.
  expect(first.getByRole("tab", { name: "Changes" }).elements()).toHaveLength(0);
  await userEvent.keyboard("{Enter}");
  expect(first.getByRole("tab").elements()).toHaveLength(0);
});

test("a note's revision: its Markdown, its source, and its words changed", async () => {
  const note = (version: number, text: string): RevisionShown => ({
    version,
    kind: "note",
    data: { text },
    by: "You",
  });
  const screen = await shown([note(1, "# Plan\n\nShip Monday"), note(2, "# Plan\n\nShip Tuesday")]);
  const latest = screen.getByRole("listitem", { name: "Version 2" });
  await expect.element(latest.getByText("Changed the Markdown")).toBeVisible();
  await expect.element(latest.getByRole("deletion")).toHaveTextContent("removed: Monday");
  await userEvent.click(latest.getByRole("tab", { name: "Preview" }));
  await expect.element(latest.getByRole("heading", { name: "Plan" })).toBeVisible();
});

test("a kind without a renderer: its JSON as a tree, its long strings unescaped", async () => {
  const plan = (version: number, steps: string[]): RevisionShown => ({
    version,
    kind: "plan",
    data: { title: "Launch", notes: 'First line\nSecond "quoted" line', steps },
    by: "Ada",
  });
  const screen = await shown([plan(1, ["draft"]), plan(2, ["draft", "ship"])]);
  const latest = screen.getByRole("listitem", { name: "Version 2" });
  await expect.element(latest.getByText("Changed the JSON (+2 −1)")).toBeVisible();
  await userEvent.click(latest.getByRole("tab", { name: "Preview" }));
  // In the Preview's panel: the Changes panel, leaving, holds a part named JSON of its own.
  const tree = latest
    .getByRole("tabpanel", { name: "Preview" })
    .getByRole("region", { name: "JSON" });
  await expect.element(tree.getByText('First line Second "quoted" line')).toBeVisible();
  expect(tree.element().textContent).not.toContain("\\n");
});

test("what changed, said in a line", () => {
  expect(changedSaid(null)).toBe("First version");
  expect(changedSaid([])).toBe("No change to its content");
  expect(changedSaid([{ part: { name: "outline", text: "", diff: "lines" }, changes: null }])).toBe(
    "Changed the outline",
  );
});

test("a tab panel shows a focus ring when the keyboard reaches it", async () => {
  const screen = await shown(APP_REVISIONS);
  const latest = screen.getByRole("listitem", { name: "Version 2" });
  latest.getByRole("tab", { name: "Changes" }).element().focus();
  await userEvent.keyboard("{Tab}");
  const panel = document.activeElement as HTMLElement;
  expect(panel.getAttribute("role")).toBe("tabpanel");
  expect(getComputedStyle(panel).outlineStyle).not.toBe("none");
  expect(getComputedStyle(panel).outlineWidth).not.toBe("0px");
});

test("archived while its preview runs, an app's revision stops it and gives up the tab", async () => {
  const revisions = (archived: boolean) => (
    <IntegrationsContext value={() => true}>
      <AppHostContext value={host()}>
        <Revisions
          id="art_1"
          revisions={APP_REVISIONS}
          renderers={RENDERERS}
          compare={compare}
          archived={archived}
        />
      </AppHostContext>
    </IntegrationsContext>
  );
  const screen = await render(revisions(false));
  const latest = screen.getByRole("listitem", { name: "Version 2" });
  await userEvent.click(latest.getByRole("tab", { name: "Preview" }));
  await userEvent.click(latest.getByRole("button", { name: "Run version 2" }));
  await expect
    .element(latest.getByTitle("Dice game: an app made by the agent"))
    .toBeInTheDocument();
  await screen.rerender(revisions(true));
  await expect
    .element(latest.getByRole("tab", { name: "Changes" }))
    .toHaveAttribute("aria-selected", "true");
  expect(latest.getByRole("tab", { name: "Preview" }).elements()).toHaveLength(0);
  expect(screen.container.querySelector("iframe")).toBeNull();
});

test("revisions read again, with the same data, are not compared again", async () => {
  const counted = vi.fn(compare);
  const list = (revisions: readonly RevisionShown[]) => (
    <Revisions id="art_1" revisions={revisions} renderers={RENDERERS} compare={counted} />
  );
  const screen = await render(list(APP_REVISIONS));
  await expect.element(screen.getByRole("tab", { name: "Changes" })).toBeVisible();
  const calls = counted.mock.calls.length;
  expect(calls).toBeGreaterThan(0);
  // A refetch: new objects for each revision, its data the same.
  await screen.rerender(list(APP_REVISIONS.map((revision) => ({ ...revision }))));
  await expect.element(screen.getByRole("tab", { name: "Changes" })).toBeVisible();
  expect(counted.mock.calls.length).toBe(calls);
});

test("one revision is open at a time: opening another closes it, and a newer one opens as it arrives", async () => {
  const screen = await shown(APP_REVISIONS);
  const summary = (name: string) =>
    screen
      .getByRole("listitem", { name })
      .element()
      .querySelector("[aria-expanded]") as HTMLElement;
  expect(summary("Version 2").getAttribute("aria-expanded")).toBe("true");
  expect(summary("Version 1").getAttribute("aria-expanded")).toBe("false");
  await userEvent.click(summary("Version 1"));
  await expect.poll(() => summary("Version 1").getAttribute("aria-expanded")).toBe("true");
  expect(summary("Version 2").getAttribute("aria-expanded")).toBe("false");
  await screen.rerender(
    <IntegrationsContext value={() => true}>
      <AppHostContext value={host()}>
        <Revisions
          id="art_1"
          revisions={[...APP_REVISIONS, app(3, "Dice game", "<p>Rolled</p>")]}
          renderers={RENDERERS}
          compare={compare}
        />
      </AppHostContext>
    </IntegrationsContext>,
  );
  await expect.poll(() => summary("Version 3").getAttribute("aria-expanded")).toBe("true");
  expect(summary("Version 1").getAttribute("aria-expanded")).toBe("false");
  expect(summary("Version 2").getAttribute("aria-expanded")).toBe("false");
});
