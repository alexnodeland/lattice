import { useRender } from "@base-ui/react/use-render";
import type { ReactElement, ReactNode } from "react";
import { useUiName } from "./brand";
import { Lockup } from "./marks";
import { SkipLink } from "./skip-link";
import { RING } from "./states";

/**
 * The app's frame (portalr ADR-0087): one bar along the top of the window, which stays as the
 * page scrolls, and the page beneath it at the window's full width. The bar's start holds the
 * mark (from 1024 pixels: a phone's bar has none, ADR-0085) and the switcher, then the areas;
 * its end, the corner, holds the way to search, what waits for the reader and the account.
 * Narrower than 1024 pixels the areas are the first row of the page, in its flow, not pinned.
 * There is no drawer: everything the bar holds is on it at every width. A page with no areas,
 * or nothing to search, leaves `nav` or `search` out.
 */
export function AppShell({
  home,
  switcher,
  nav,
  search,
  waiting,
  account,
  children,
}: {
  /** The link home, such as the router's, that the mark renders as. */
  home: ReactElement;
  switcher: ReactNode;
  /** The areas, a `Tracks`; none, for a page that has no areas to go between. */
  nav?: ReactNode;
  /** The way to search, an icon button; none, where there is nothing to search. */
  search?: ReactNode;
  /** What waits for the reader, a link; none, where nothing does. */
  waiting?: ReactNode;
  account: ReactNode;
  children: ReactNode;
}) {
  const name = useUiName("app");
  const mark = useRender({
    defaultTagName: "a",
    render: home,
    props: {
      "aria-label": name,
      className: `inline-flex shrink-0 rounded-(--header-trigger-radius) ${RING}`,
      children: <Lockup ui="app" mono />,
    },
  });
  return (
    <div className="flex min-h-dvh flex-col">
      <SkipLink />
      <header
        data-frame-header=""
        className="sticky top-0 z-20 flex h-[calc(var(--header-clearance)+env(safe-area-inset-top))] items-center gap-2 border-line border-b bg-paper px-2 pt-[env(safe-area-inset-top)] sm:px-4"
      >
        <span className="me-2 max-lg:hidden">{mark}</span>
        <div className="min-w-0">{switcher}</div>
        {nav && <div className="ms-2 max-lg:hidden">{nav}</div>}
        <div className="ms-auto flex shrink-0 items-center gap-1">
          {search}
          {waiting}
          {account}
        </div>
      </header>
      <main
        id="main"
        tabIndex={-1}
        // One rhythm (portalr ADR-0085): 24px between a page's parts on a phone, 32px from 1024.
        className="flex min-w-0 flex-1 flex-col gap-6 px-4 py-6 outline-none sm:px-6 lg:gap-8 lg:px-8"
      >
        {nav && <div className="lg:hidden">{nav}</div>}
        {children}
      </main>
    </div>
  );
}
