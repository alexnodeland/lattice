/**
 * A new version, offered to a tab that outlived it (portalr ADR-0058). The page a UI is served
 * as names its build by its entry script, whose name is its content's hash: read again every
 * few minutes, and when the tab comes back into view, a different one is a new build. The
 * person is told, politely, in a live region, and chooses: "Reload", or "Not now", which holds
 * for that build. Nothing reloads by itself, so nothing typed is lost.
 */

import { RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "./button";
import { Icon } from "./icon";

/** How often the page is read again, in milliseconds, while the tab is open. */
const EVERY = 5 * 60_000;

/** Where a build the person said "Not now" to is kept, for this browser. */
const DISMISSED = "portalr:not-now";

/** A page's build: its entry module script's address, or null where it names none. */
export function buildOf(html: string): string | null {
  const page = new DOMParser().parseFromString(html, "text/html");
  return page.querySelector('script[type="module"][src]')?.getAttribute("src") ?? null;
}

const dismissed = () => {
  try {
    return localStorage.getItem(DISMISSED);
  } catch {
    return null; // storage refused: the offer is made again
  }
};

/**
 * The newer build the tab's page has been replaced by, or null: `page` is the UI's own address,
 * read again every `every` milliseconds, on focus, and when the tab is shown again.
 */
function useNewVersion(page: string, every = EVERY): string | null {
  const [newer, setNewer] = useState<string | null>(null);
  useEffect(() => {
    const running = buildOf(document.documentElement.outerHTML);
    if (running === null) {
      return; // a page with no built entry, as in development: nothing to compare
    }
    let stopped = false;
    const check = async () => {
      if (document.visibilityState === "hidden") {
        return;
      }
      try {
        const asked = new Request(new URL(page, location.href), { cache: "no-store" });
        const served = buildOf(await (await fetch(asked)).text());
        if (!stopped && served !== null && served !== running && served !== dismissed()) {
          setNewer(served);
        }
      } catch {
        // offline, or the server is restarting: asked again at the next turn
      }
    };
    const timer = setInterval(check, every);
    addEventListener("focus", check);
    document.addEventListener("visibilitychange", check);
    return () => {
      stopped = true;
      clearInterval(timer);
      removeEventListener("focus", check);
      document.removeEventListener("visibilitychange", check);
    };
  }, [page, every]);
  return newer;
}

/** The offer of a new build, `build`: "Reload", or "Not now" for that build. */
export function NewVersion({
  build,
  onReload = () => location.reload(),
  onDismiss,
}: {
  build: string;
  onReload?: () => void;
  onDismiss: () => void;
}) {
  const notNow = () => {
    try {
      localStorage.setItem(DISMISSED, build);
    } catch {
      // storage refused: dismissed for this page alone
    }
    onDismiss();
  };
  return (
    <div
      role="status"
      aria-label="A new version"
      className="fixed inset-x-4 top-4 z-50 mx-auto flex max-w-md flex-wrap items-center gap-3 rounded-lg border border-line bg-surface p-3 text-fg text-sm shadow-lg"
    >
      <Icon icon={RefreshCw} className="size-4 shrink-0" />
      <p className="min-w-0 flex-1">A new version of portalr is ready. Reload to use it.</p>
      <span className="flex gap-2">
        <Button variant="secondary" onClick={notNow}>
          Not now
        </Button>
        <Button onClick={onReload}>Reload</Button>
      </span>
    </div>
  );
}

/** The offer, made in a UI served at `page` once its build is replaced. */
export function NewVersionOffer({ page }: { page: string }) {
  const newer = useNewVersion(page);
  const [shown, setShown] = useState<string | null>(null);
  useEffect(() => setShown(newer), [newer]);
  return shown === null ? null : <NewVersion build={shown} onDismiss={() => setShown(null)} />;
}
