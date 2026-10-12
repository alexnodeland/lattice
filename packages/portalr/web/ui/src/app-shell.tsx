import { Dialog } from "@base-ui/react/dialog";
import { useRender } from "@base-ui/react/use-render";
import { Menu as MenuGlyph, X } from "lucide-react";
import { type MouseEvent, type ReactElement, type ReactNode, useState } from "react";
import { Icon } from "./icon";
import { Lockup, Mark, type Ui } from "./marks";

/** The UI's name, which its mark pictures. */
const NAME: Record<Ui, string> = { app: "portalr", admin: "portalr admin" };

/** The mark, as a link home, named for the UI: the lockup on the rail, the mark alone above. */
function Home({ ui, home, mark }: { ui: Ui; home: ReactElement; mark: ReactNode }) {
  return useRender({
    defaultTagName: "a",
    render: home,
    props: {
      "aria-label": NAME[ui],
      className:
        "inline-flex shrink-0 rounded-md outline-offset-2 focus-visible:outline-2 focus-visible:outline-focus",
      children: mark,
    },
  });
}

const button =
  "inline-flex items-center gap-2 rounded-md px-2 py-1.5 font-semibold text-fg text-sm outline-offset-2 hover:bg-wash focus-visible:outline-2 focus-visible:outline-focus";

/**
 * The frame of every signed-in screen. From 1024 pixels, a rail on the surface holds the lockup,
 * the switcher, the navigation and the account, and stays as the page scrolls. Narrower, a bar
 * holds the mark, the switcher and the account, and Menu opens the navigation in a drawer, a
 * Base UI dialog that keeps the focus in it, closes on Escape or on following a link, and gives
 * the focus back to Menu. `ui` chooses the mark: `admin`'s opens to the other side.
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
      <header className="sticky top-0 z-20 flex items-center gap-1 border-line border-b bg-surface px-3 py-2 lg:hidden">
        <Dialog.Root open={open} onOpenChange={setOpen}>
          <Dialog.Trigger className={button}>
            <Icon icon={MenuGlyph} />
            Menu
          </Dialog.Trigger>
          <Dialog.Portal>
            <Dialog.Backdrop className="fixed inset-0 z-40 bg-scrim transition-opacity duration-200 data-ending-style:opacity-0 data-starting-style:opacity-0 motion-reduce:transition-none" />
            <Dialog.Popup
              onClick={followed}
              className="fixed inset-y-0 left-0 z-50 flex w-[min(19rem,85vw)] flex-col gap-4 border-line border-r bg-surface p-3 text-fg outline-none transition-transform duration-200 data-ending-style:-translate-x-full data-starting-style:-translate-x-full motion-reduce:transition-none"
            >
              <div className="flex items-center justify-between pl-2">
                <Dialog.Title className="sr-only">Navigation</Dialog.Title>
                <Home ui={ui} home={home} mark={<Lockup ui={ui} />} />
                <Dialog.Close className={button}>
                  <Icon icon={X} />
                  Close
                </Dialog.Close>
              </div>
              {nav}
            </Dialog.Popup>
          </Dialog.Portal>
        </Dialog.Root>
        <Home ui={ui} home={home} mark={<Mark ui={ui} />} />
        <div className="ml-1 min-w-0 flex-1">{switcher}</div>
        {account}
      </header>
      <aside className="sticky top-0 hidden h-dvh flex-col gap-4 border-line border-r bg-surface p-3 lg:flex">
        <div className="px-2 pt-3 pb-1">
          <Home ui={ui} home={home} mark={<Lockup ui={ui} />} />
        </div>
        {switcher}
        <div className="flex-1 overflow-y-auto">{nav}</div>
        <div className="border-line border-t pt-3">{account}</div>
      </aside>
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
