import { useEffect, useState } from "react";
import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { useHeadingAfterNavigation } from "./after-navigation";

/** A router's `onResolved`, as a test sends it. */
function resolver() {
  const listeners = new Set<(event: { pathChanged: boolean }) => void>();
  return {
    subscribe: (listener: (event: { pathChanged: boolean }) => void) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    resolve: (pathChanged: boolean) => {
      for (const listener of listeners) listener({ pathChanged });
    },
  };
}

function Page({
  subscribe,
  late,
}: {
  subscribe: ReturnType<typeof resolver>["subscribe"];
  late: number;
}) {
  useHeadingAfterNavigation(subscribe);
  const [shown, setShown] = useState(late === 0);
  useEffect(() => {
    const timer = setTimeout(() => setShown(true), late);
    return () => clearTimeout(timer);
  }, [late]);
  return <main id="main">{shown && <h1>The page</h1>}</main>;
}

const frames = () =>
  new Promise((settled) => requestAnimationFrame(() => requestAnimationFrame(settled)));

test("after a navigation that changed the path, the focus goes to the page's heading", async () => {
  const router = resolver();
  const screen = await render(<Page subscribe={router.subscribe} late={0} />);
  router.resolve(false);
  await frames();
  expect(document.activeElement).toBe(document.body);
  router.resolve(true);
  await expect.element(screen.getByRole("heading", { name: "The page" })).toHaveFocus();
});

test("a heading drawn late is waited for, a while", async () => {
  const router = resolver();
  const screen = await render(<Page subscribe={router.subscribe} late={200} />);
  router.resolve(true);
  await expect.element(screen.getByRole("heading", { name: "The page" })).toHaveFocus();
});

test("focus somewhere already stays there", async () => {
  const router = resolver();
  const screen = await render(
    <>
      <button type="button">Rail</button>
      <Page subscribe={router.subscribe} late={0} />
    </>,
  );
  (screen.getByRole("button", { name: "Rail" }).element() as HTMLElement).focus();
  router.resolve(true);
  await frames();
  await frames();
  await expect.element(screen.getByRole("button", { name: "Rail" })).toHaveFocus();
});

test("gone before it could, it does nothing", async () => {
  const router = resolver();
  const screen = await render(<Page subscribe={router.subscribe} late={5_000} />);
  router.resolve(true);
  await screen.unmount();
  router.resolve(true);
  await frames();
  expect(document.activeElement).toBe(document.body);
});
