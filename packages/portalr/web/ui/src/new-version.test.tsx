import { afterEach, expect, test, vi } from "vitest";
import { render } from "vitest-browser-react";
import { buildOf, NewVersion, NewVersionOffer } from "./new-version";

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.removeItem("portalr:not-now");
});

/** A UI's page, as served, whose entry is `entry`. */
const served = (entry: string) =>
  `<!doctype html><html><head><script src="/scheme.js"></script><script type="module" crossorigin src="${entry}"></script></head><body><div id="root"></div></body></html>`;

/** The page's address answered with a page of `entry`, and what was asked. */
function serving(entry: string) {
  const fetched = vi.fn(async () => new Response(served(entry)));
  vi.stubGlobal("fetch", fetched);
  return fetched;
}

const running = () => buildOf(document.documentElement.outerHTML) ?? "";

test("a page's build is its entry module script, and a page with none has none", () => {
  expect(buildOf(served("/portalr/app/assets/index-Ab12.js"))).toBe(
    "/portalr/app/assets/index-Ab12.js",
  );
  expect(buildOf("<p>No scripts</p>")).toBeNull();
});

test("a tab whose page was replaced is offered the new build when it comes back into view", async () => {
  const fetched = serving("/portalr/app/assets/index-New1.js");
  const screen = await render(<NewVersionOffer page="/portalr/app/" />);
  dispatchEvent(new Event("focus"));
  const offer = screen.getByRole("status", { name: "A new version" });
  await expect.element(offer).toBeVisible();
  await expect
    .element(offer.getByText("A new version of portalr is ready. Reload to use it."))
    .toBeVisible();
  const [asked] = fetched.mock.calls[0] as unknown as [Request];
  expect([new URL(asked.url).pathname, asked.cache]).toEqual(["/portalr/app/", "no-store"]);
});

test("Not now holds for that build: asked again, it isn't offered", async () => {
  const fetched = serving("/portalr/app/assets/index-New2.js");
  const screen = await render(<NewVersionOffer page="/portalr/app/" />);
  dispatchEvent(new Event("focus"));
  await screen.getByRole("button", { name: "Not now" }).click();
  await expect
    .element(screen.getByRole("status", { name: "A new version" }))
    .not.toBeInTheDocument();
  expect(localStorage.getItem("portalr:not-now")).toBe("/portalr/app/assets/index-New2.js");
  const before = fetched.mock.calls.length;
  dispatchEvent(new Event("focus"));
  await vi.waitFor(() => expect(fetched.mock.calls.length).toBeGreaterThan(before));
  await new Promise((settled) => setTimeout(settled, 50));
  await expect
    .element(screen.getByRole("status", { name: "A new version" }))
    .not.toBeInTheDocument();
});

test("the same build is no new version", async () => {
  const fetched = serving(running());
  const screen = await render(<NewVersionOffer page="/portalr/app/" />);
  dispatchEvent(new Event("focus"));
  await vi.waitFor(() => expect(fetched).toHaveBeenCalled());
  await new Promise((settled) => setTimeout(settled, 50));
  expect(screen.container.querySelector('[role="status"]')).toBeNull();
});

test("Reload is the person's to choose, by the keyboard too", async () => {
  const onReload = vi.fn();
  const screen = await render(<NewVersion build="b" onReload={onReload} onDismiss={() => {}} />);
  const reload = screen.getByRole("button", { name: "Reload" });
  (reload.element() as HTMLButtonElement).focus();
  await expect.element(reload).toHaveFocus();
  await reload.click();
  expect(onReload).toHaveBeenCalledOnce();
});
