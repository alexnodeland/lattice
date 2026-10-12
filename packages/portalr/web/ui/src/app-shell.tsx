import { Dialog } from "@base-ui/react/dialog";
import { useRender } from "@base-ui/react/use-render";
import { Menu as MenuGlyph, X } from "lucide-react";
import { type MouseEvent, type ReactElement, type ReactNode, useEffect, useState } from "react";
import { Icon } from "./icon";
import { Lockup, Mark, type Ui } from "./marks";

/** The UI's name, which its mark pictures. */
const NAME: Record<Ui, string> = { app: "portalr", admin: "portalr admin" };

/** From this width the frame is a rail, and the drawer has no place. */
const WIDE = "(min-width: 1024px)";

/** The mark, as a link home named for the UI. */
function Home({ ui, home, children }: { ui: Ui; home: ReactElement; children: ReactNode }) {
  return useRender({
    defaultTagName: "a",
    render: home,
    props: {
      "aria-label": NAME[ui],
      className:
        "inline-flex shrink-0 rounded-md outline-offset-2 focus-visible:outline-2 focus-visible:outline-focus",
      children,
    },
  });
}

const button =
  "inline-flex items-center gap-2 rounded-md px-2 py-1.5 font-semibold text-fg text-sm outline-offset-2 hover:bg-wash focus-visible:outline-2 focus-visible:outline-focus";

/**
 * The frame of every signed-in screen. One header holds the mark, the switcher, the navigation
 * and the account, each rendered once: from 1024 pixels it is a rail on the surface that stays as
 * the page scrolls; narrower, it is a bar of the mark, the switcher and the account, and Menu opens
 * the navigation in a drawer. The drawer is a Base UI dialog that keeps the focus, closes on
 * Escape, on Close, on following a link or on widening past the rail's width, and gives the focus
 * back to Menu. `ui` chooses the mark: `admin`'s opens to the other side.
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
  /** The navigation, a `SideNav`. */
  nav: ReactNode;
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
    <div className="min-h-dvh bg-paper text-fg lg:grid lg:grid-cols-[15.5rem_minmax(0,1fr)]">
      <a
        href="#main"
        className="fixed top-2 left-2 z-50 -translate-y-16 rounded-md bg-surface px-3 py-2 font-semibold text-sm focus:translate-y-0 focus-visible:outline-2 focus-visible:outline-focus"
      >
        Skip to content
      </a>
      <header className="sticky top-0 z-20 flex items-center gap-1 border-line border-b bg-surface px-3 py-2 lg:h-dvh lg:flex-col lg:items-stretch lg:gap-4 lg:border-r lg:border-b-0 lg:p-3">
        <Dialog.Root open={open} onOpenChange={setOpen}>
          <Dialog.Trigger className={`${button} lg:hidden`}>
            <Icon icon={MenuGlyph} />
            Menu
          </Dialog.Trigger>
          <Dialog.Portal>
            <Dialog.Backdrop className="fixed inset-0 z-40 bg-scrim transition-opacity duration-200 data-ending-style:opacity-0 data-starting-style:opacity-0 motion-reduce:transition-none" />
            <Dialog.Popup
              aria-modal="true"
              onClick={followed}
              className="fixed inset-y-0 left-0 z-50 flex w-[min(19rem,85vw)] flex-col gap-4 border-line border-r bg-surface p-3 text-fg outline-none transition-transform duration-200 data-ending-style:-translate-x-full data-starting-style:-translate-x-full motion-reduce:transition-none"
            >
              <div className="flex items-center justify-between pl-2">
                <Dialog.Title className="sr-only">Navigation</Dialog.Title>
                <Home ui={ui} home={home}>
                  <Lockup ui={ui} />
                </Home>
                <Dialog.Close className={button}>
                  <Icon icon={X} />
                  Close
                </Dialog.Close>
              </div>
              {nav}
            </Dialog.Popup>
          </Dialog.Portal>
        </Dialog.Root>
        <div className="lg:px-2 lg:pt-3 lg:pb-1">
          <Home ui={ui} home={home}>
            <Mark ui={ui} className="lg:hidden" />
            <Lockup ui={ui} className="max-lg:hidden" />
          </Home>
        </div>
        <div className="ml-1 min-w-0 flex-1 lg:ml-0 lg:flex-none">{switcher}</div>
        <div className="hidden flex-1 overflow-y-auto lg:block">{nav}</div>
        <div className="lg:border-line lg:border-t lg:pt-3">{account}</div>
      </header>
      <main
        id="main"
        tabIndex={-1}
        className="min-w-0 px-4 py-6 outline-none sm:px-6 lg:px-12 lg:py-9"
      >
        <div className="max-w-260">{children}</div>
      </main>
    </div>
  );
}
