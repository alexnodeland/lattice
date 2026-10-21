import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { render } from "vitest-browser-react";
import { buildOf, NewVersion, NewVersionOffer } from "./new-version";

const PAGE = "/portalr/app/";
const RUNNING = `${PAGE}assets/index-Old.js`;
const KEY = `portalr:not-now:${PAGE}`;

/** The tab's own page names its build, as a built UI's does. */
let entry: HTMLScriptElement;
beforeEach(() => {
  entry = document.createElement("script");
  entry.type = "module";
  entry.setAttribute("src", RUNNING);
  document.head.append(entry);
});

afterEach(() => {
  entry.remove();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  localStorage.removeItem(KEY);
});

/** A UI's page, as served, whose entry is `src`, after another module script of no build. */
const page = (src: string) =>
  `<!doctype html><html><head><script type="module" src="/extension.js"></script><script type="module" crossorigin src="${src}"></script></head><body></body></html>`;

type Answer = () => Response | Promise<Response>;

/** The page's address answered by each of `answers` in turn, the last again after them. */
function serving(...answers: Answer[]) {
  let asked = 0;
  const fetched = vi.fn(async () => (answers[Math.min(asked++, answers.length - 1)] as Answer)());
  vi.stubGlobal("fetch", fetched);
  return fetched;
}

const html = (src: string) => () =>
  new Response(page(src), { headers: { "content-type": "text/html; charset=utf-8" } });

/** The tab shown again, as when the person comes back to it. */
const shown = () => document.dispatchEvent(new Event("visibilitychange"));

/** Every read so far answered and acted on. */
async function answered(fetched: ReturnType<typeof serving>, reads: number) {
  await vi.waitFor(() => expect(fetched.mock.results.length).toBeGreaterThanOrEqual(reads));
  await Promise.allSettled(fetched.mock.results.map((result) => result.value));
  await new Promise((settled) => setTimeout(settled, 0));
}

/** The offer's Reload. */
const offered = (screen: Awaited<ReturnType<typeof render>>) =>
  screen.getByRole("button", { name: "Reload" });

test("a page's build is its entry under the UI's assets, whatever module script comes first", () => {
  const parsed = new DOMParser().parseFromString(page(`${PAGE}assets/index-Ab12.js`), "text/html");
  expect(buildOf(parsed, PAGE)).toBe(`${PAGE}assets/index-Ab12.js`);
  expect(buildOf(parsed, "/portalr/admin/")).toBeNull();
  expect(buildOf(new DOMParser().parseFromString("<p>Sign in</p>", "text/html"), PAGE)).toBeNull();
});

test("the live region is there before anything is offered in it", async () => {
  serving(html(RUNNING));
  const screen = await render(<NewVersionOffer ui="app" page={PAGE} />);
  const region = screen.container.querySelector('[aria-live="polite"]');
  expect(region).not.toBeNull();
  expect(region?.childElementCount).toBe(0);
  expect(document.querySelector('[role="status"]')).toBeNull();
});

test("a new build, read twice running, is offered when the tab is shown again", async () => {
  const fetched = serving(html(`${PAGE}assets/index-New.js`));
  const screen = await render(<NewVersionOffer ui="app" page={PAGE} />);
  shown();
  await answered(fetched, 1);
  expect(screen.container.querySelector("button")).toBeNull();
  shown();
  await expect.element(offered(screen)).toBeVisible();
  await expect
    .element(screen.getByText("A new version of portalr is ready. Reload to use it."))
    .toBeVisible();
  const [asked] = fetched.mock.calls[0] as unknown as [Request];
  expect([new URL(asked.url).pathname, asked.cache]).toEqual([PAGE, "no-store"]);
});

test("the page is read again on its own, every so often", async () => {
  serving(html(`${PAGE}assets/index-New.js`));
  const screen = await render(<NewVersionOffer ui="admin" page={PAGE} every={20} />);
  await expect
    .element(screen.getByText("A new version of portalr admin is ready. Reload to use it."))
    .toBeVisible();
});

const failing =
  (status: number, type = "text/html") =>
  () =>
    new Response(page(`${PAGE}assets/index-New.js`), { status, headers: { "content-type": type } });

test.each<[string, Answer]>([
  ["a sign-in page", html("/sign-in/assets/index-New.js")],
  [
    "a captive portal's page",
    () => new Response("<p>Accept the terms</p>", { headers: { "content-type": "text/html" } }),
  ],
  ["a server failing", failing(503)],
  ["a page not found", failing(404)],
  ["something not a page", failing(200, "application/json")],
  [
    "a redirect elsewhere",
    () => {
      const answer = html(`${PAGE}assets/index-New.js`)();
      Object.defineProperty(answer, "redirected", { value: true });
      return answer;
    },
  ],
  ["no network", () => Promise.reject(new TypeError("Failed to fetch"))],
  ["the same build", html(RUNNING)],
])("%s is no new build", async (_, answer) => {
  const fetched = serving(answer);
  const screen = await render(<NewVersionOffer ui="app" page={PAGE} />);
  shown();
  shown();
  shown();
  await answered(fetched, 3);
  expect(screen.container.querySelector("button")).toBeNull();
});

test("builds that flap, as in a rolling deploy, aren't offered", async () => {
  const fetched = serving(
    html(`${PAGE}assets/index-A.js`),
    html(`${PAGE}assets/index-B.js`),
    html(`${PAGE}assets/index-A.js`),
    html(`${PAGE}assets/index-B.js`),
  );
  const screen = await render(<NewVersionOffer ui="app" page={PAGE} />);
  for (let read = 0; read < 4; read += 1) {
    shown();
    await answered(fetched, read + 1);
  }
  expect(screen.container.querySelector("button")).toBeNull();
});

test("Not now holds for that build in this UI alone", async () => {
  serving(html(`${PAGE}assets/index-New.js`));
  const screen = await render(<NewVersionOffer ui="app" page={PAGE} />);
  shown();
  shown();
  await screen.getByRole("button", { name: "Not now" }).click();
  await expect.element(offered(screen)).not.toBeInTheDocument();
  expect(localStorage.getItem(KEY)).toBe(`${PAGE}assets/index-New.js`);
  expect(localStorage.getItem("portalr:not-now:/portalr/admin/")).toBeNull();
});

test("Not now said in another tab is heard in this one", async () => {
  serving(html(`${PAGE}assets/index-New.js`));
  const screen = await render(<NewVersionOffer ui="app" page={PAGE} />);
  shown();
  shown();
  await expect.element(offered(screen)).toBeVisible();
  localStorage.setItem(KEY, `${PAGE}assets/index-New.js`);
  dispatchEvent(new StorageEvent("storage", { key: KEY }));
  await expect.element(offered(screen)).not.toBeInTheDocument();
});

test("storage refused, Not now still holds for this page", async () => {
  serving(html(`${PAGE}assets/index-New.js`));
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new DOMException("refused", "SecurityError");
  });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new DOMException("refused", "SecurityError");
  });
  const screen = await render(<NewVersionOffer ui="app" page={PAGE} />);
  shown();
  shown();
  await screen.getByRole("button", { name: "Not now" }).click();
  await expect.element(offered(screen)).not.toBeInTheDocument();
});

test("unmounted, the page is read no more", async () => {
  const fetched = serving(html(RUNNING));
  const screen = await render(<NewVersionOffer ui="app" page={PAGE} every={20} />);
  await answered(fetched, 1);
  await screen.unmount();
  const reads = fetched.mock.calls.length;
  shown();
  await new Promise((settled) => setTimeout(settled, 100));
  expect(fetched.mock.calls.length).toBe(reads);
});

test("Reload is the person's to choose, by the keyboard too", async () => {
  const onReload = vi.fn();
  const screen = await render(<NewVersion ui="app" onReload={onReload} onDismiss={() => {}} />);
  const reload = screen.getByRole("button", { name: "Reload" });
  (reload.element() as HTMLButtonElement).focus();
  await expect.element(reload).toHaveFocus();
  await reload.click();
  expect(onReload).toHaveBeenCalledOnce();
});
