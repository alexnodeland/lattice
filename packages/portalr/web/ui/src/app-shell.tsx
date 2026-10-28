import { Dialog } from "@base-ui/react/dialog";
import { useRender } from "@base-ui/react/use-render";
import { type MouseEvent, type ReactElement, type ReactNode, useEffect, useState } from "react";
import { useBrand, useUiName } from "./brand";
import { cn } from "./cn";
import { backdrop } from "./dialog";
import { keepTabWithin } from "./full-view";
import { Icon } from "./icon";
import { glyphs } from "./icons";
import { Lockup, type Ui } from "./marks";
import { SkipLink } from "./skip-link";
import { FEEDBACK, RING } from "./states";

/** From this width the frame is a rail, and the drawer has no place. */
const WIDE = "(min-width: 1024px)";

/** The mark, as a link home named for the UI. */
function Home({ ui, home, children }: { ui: Ui; home: ReactElement; children: ReactNode }) {
  const name = useUiName(ui);
  // A kit's name may be long: it is cut to the room, and said whole on hover.
  const kit = useBrand() !== null;
  return useRender({
    defaultTagName: "a",
    render: home,
    props: {
      "aria-label": name,
      title: kit ? name : undefined,
      className: cn(
        "inline-flex rounded-(--header-trigger-radius)",
        RING,
        kit ? "min-w-0 max-w-full" : "shrink-0",
      ),
      children,
    },
  });
}

const button = cn(
  "inline-flex items-center gap-2 rounded-(--header-trigger-radius) px-2 py-(--header-trigger-pad-y) font-semibold text-fg text-sm hover:bg-wash",
  RING,
  FEEDBACK,
);

/**
 * The frame of every signed-in screen. One header holds the mark, the switcher, the navigation
 * and the account: from 1024 pixels it is a rail on the paper, set apart by space alone (portalr ADR-0080), that stays as the page scrolls;
 * narrower, it is a bar of the mark, the switcher and the account, and Menu opens a drawer that
 * holds the switcher, the navigation and the account too, whose name is shown. While the drawer
 * is open, then, each is there twice, behind it and in it. The drawer is a Base UI dialog that
 * keeps the focus, closes on Escape, on Close, on following a link or on widening past the
 * rail's width, and gives the focus back to Menu. `ui` chooses the mark: `admin`'s opens to the
 * other side. A page with no navigation of its own leaves `nav` out.
 */
export function AppShell({
  ui = "app",
  home,
  switcher,
  nav,
  account,
  children,
}: {
  ui?: Ui;
  /** The link home, such as the router's, that the mark renders as. */
  home: ReactElement;
  switcher: ReactNode;
  /** The navigation, a `SideNav`; none, for a page that has no areas to go between. */
  nav?: ReactNode;
  account: ReactNode;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const wide = matchMedia(WIDE);
    const close = () => {
      if (wide.matches) {
        setOpen(false);
      }
    };
    wide.addEventListener("change", close);
    return () => wide.removeEventListener("change", close);
  }, []);
  function followed(event: MouseEvent<HTMLElement>) {
    if (event.target instanceof Element && event.target.closest("a")) {
      setOpen(false);
    }
  }
  return (
    <div
      data-density={ui === "admin" ? "compact" : undefined}
      className="min-h-dvh lg:grid lg:grid-cols-[var(--rail-width)_minmax(0,1fr)]"
    >
      <SkipLink />
      <header
        data-frame-header=""
        className="sticky top-0 z-20 flex items-center gap-1 bg-paper px-3 pt-[calc(var(--space-2)+env(safe-area-inset-top))] pb-2 lg:h-dvh lg:flex-col lg:items-stretch lg:gap-4 lg:p-3"
      >
        <Dialog.Root open={open} onOpenChange={setOpen}>
          {/* The glyph alone on a phone's bar, which keeps its room for the switcher (portalr ADR-0085). */}
          <Dialog.Trigger aria-label="Menu" className={`${button} lg:hidden`}>
            <Icon icon={glyphs.menu} />
          </Dialog.Trigger>
          <Dialog.Portal>
            <Dialog.Backdrop className={backdrop} />
            <Dialog.Popup
              aria-modal="true"
              onClick={followed}
              // Tab kept in it at once, never on Base UI's guards outside it (portalr ADR-0068).
              onKeyDown={(event) => keepTabWithin(event.currentTarget, event.nativeEvent)}
              data-frame-drawer=""
              className="fixed inset-y-0 left-0 z-50 flex w-[min(var(--drawer-width),85vw)] flex-col gap-4 border-line border-r bg-surface p-3 text-fg shadow-(--drawer-shadow) outline-none transition-transform duration-(--drawer-duration) data-ending-style:-translate-x-full data-starting-style:-translate-x-full motion-reduce:transition-none"
            >
              <div className="flex items-center justify-between pl-2">
                <Dialog.Title className="sr-only">Navigation</Dialog.Title>
                <Home ui={ui} home={home}>
                  <Lockup ui={ui} mono />
                </Home>
                <Dialog.Close className={button}>
                  <Icon icon={glyphs.x} />
                  Close
                </Dialog.Close>
              </div>
              <div className="px-1">{switcher}</div>
              <div className="flex-1 overflow-y-auto">{nav}</div>
              <div data-drawer="" className="border-line border-t pt-3">
                {account}
              </div>
            </Dialog.Popup>
          </Dialog.Portal>
        </Dialog.Root>
        {/* The lockup in the one colour, on the rail alone: a phone's bar leaves the mark out
            (portalr ADR-0085), and the drawer holds the way home. */}
        <div className="max-lg:hidden lg:px-2 lg:pt-3 lg:pb-1">
          <Home ui={ui} home={home}>
            <Lockup ui={ui} mono />
          </Home>
        </div>
        <div className="min-w-0 flex-1 lg:flex-none">{switcher}</div>
        {nav ? (
          <div className="hidden flex-1 overflow-y-auto lg:block">{nav}</div>
        ) : (
          <div className="hidden lg:block lg:flex-1" />
        )}
        <div className="lg:pt-3">{account}</div>
      </header>
      <main
        id="main"
        tabIndex={-1}
        className="min-w-0 px-4 py-6 outline-none sm:px-6 lg:px-12 lg:py-10"
      >
        {/* One rhythm (portalr ADR-0085): 24px between a page's parts on a phone, 32px from the rail. */}
        <div className="mx-auto flex w-full max-w-(--page-width) flex-col gap-6 lg:gap-8">
          {children}
        </div>
      </main>
    </div>
  );
}
