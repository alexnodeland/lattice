/**
 * A new version, offered to a tab that outlived it (portalr ADR-0058). The page a UI is served
 * as names its build by its entry script, `<page>assets/index-<hash>.js`, whose name is its
 * content's hash: read again every few minutes, and when the tab is shown again, a different one,
 * read twice running, is a new build. The person is told, politely, in a live region that is
 * always there, and chooses: "Reload", or "Not now", which holds for that build in that UI.
 * Nothing reloads by itself.
 */

import { RefreshCw } from "lucide-react";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { brandName, useBrand } from "./brand";
import { Button } from "./button";
import { Icon } from "./icon";
import { UI_NAME, type Ui } from "./marks";

/** How often the page is read again, in milliseconds, while the tab is open. */
const EVERY = 5 * 60_000;

/** Where a build the person said "Not now" to is kept, per UI, for this browser. */
const dismissedKey = (page: string) => `portalr:not-now:${page}`;

/** A page's build: its first module script whose address is under `page`'s assets, or null. */
export function buildOf(root: ParentNode, page: string): string | null {
  for (const script of root.querySelectorAll('script[type="module"][src]')) {
    const src = script.getAttribute("src") ?? "";
    if (src.startsWith(`${page}assets/`)) {
      return src;
    }
  }
  return null;
}

/** The build a page served as `page` names, read afresh, or null for anything but that page. */
async function served(page: string, signal: AbortSignal): Promise<string | null> {
  const asked = new Request(new URL(page, location.href), { cache: "no-store", signal });
  const answer = await fetch(asked);
  // A sign-in page, a captive portal or a server failing is no build.
  if (!answer.ok || answer.redirected || !answer.headers.get("content-type")?.includes("html")) {
    return null;
  }
  return buildOf(new DOMParser().parseFromString(await answer.text(), "text/html"), page);
}

const read = (key: string) => {
  try {
    return localStorage.getItem(key);
  } catch {
    return null; // storage refused: the offer is made again
  }
};

/** The build "Not now" holds for in this UI, kept in step with the browser's other tabs. */
function useDismissed(page: string): [string | null, (build: string) => void] {
  const key = dismissedKey(page);
  const [here, setHere] = useState<string | null>(null);
  const stored = useSyncExternalStore(
    (changed) => {
      addEventListener("storage", changed);
      return () => removeEventListener("storage", changed);
    },
    () => read(key),
  );
  const dismiss = (build: string) => {
    setHere(build);
    try {
      localStorage.setItem(key, build);
    } catch {
      // storage refused: dismissed for this page alone
    }
  };
  return [here ?? stored, dismiss];
}

/**
 * The newer build the tab's page has been replaced by, or null: `page` is the UI's own address,
 * read again every `every` milliseconds and whenever the tab is shown again; a build is newer
 * once it is read twice running, so a rolling deploy or a rollback isn't offered mid-flight.
 */
function useNewVersion(page: string, every: number): string | null {
  const [newer, setNewer] = useState<string | null>(null);
  useEffect(() => {
    // In development the entry is the source (`src/main.tsx`), under no `assets/`: no build.
    const running = buildOf(document, page);
    if (running === null) {
      return;
    }
    const stop = new AbortController();
    let last: string | null = null;
    const check = async () => {
      if (stop.signal.aborted || document.visibilityState === "hidden") {
        return;
      }
      try {
        const build = await served(page, stop.signal);
        if (build !== null && build !== running && build === last) {
          setNewer(build);
        }
        last = build;
      } catch {
        // offline, aborted, or the server is restarting: asked again at the next turn
      }
    };
    const timer = setInterval(check, every);
    document.addEventListener("visibilitychange", check);
    return () => {
      stop.abort();
      clearInterval(timer);
      document.removeEventListener("visibilitychange", check);
    };
  }, [page, every]);
  return newer;
}

/** The offer of a new build of the UI `ui`: "Reload", or "Not now" for it. */
export function NewVersion({
  ui,
  onReload = () => location.reload(),
  onDismiss,
}: {
  ui: Ui;
  onReload?: () => void;
  onDismiss: () => void;
}) {
  const brand = useBrand();
  return (
    <div className="pointer-events-auto mx-auto flex max-w-(--notice-width) flex-wrap items-center gap-3 rounded-(--notice-radius) border border-line bg-surface p-(--notice-pad) text-fg text-sm shadow-(--notice-shadow)">
      <Icon icon={RefreshCw} className="size-4 shrink-0" />
      <p className="min-w-0 flex-1">
        A new version of {brand ? brandName(brand, ui) : UI_NAME[ui]} is ready. Reload to use it.
      </p>
      <span className="flex gap-2">
        <Button variant="secondary" onClick={onDismiss}>
          Not now
        </Button>
        <Button onClick={onReload}>Reload</Button>
      </span>
    </div>
  );
}

/**
 * The offer, made in the UI `ui` served at `page` once its build is replaced, in a live region
 * that is always there, so what appears in it is announced. It sits below a narrow window's bar
 * and the skip link, and passes clicks through where it draws nothing.
 */
export function NewVersionOffer({
  ui,
  page,
  every = EVERY,
}: {
  ui: Ui;
  page: string;
  every?: number;
}) {
  const newer = useNewVersion(page, every);
  const [dismissed, dismiss] = useDismissed(page);
  const region = useRef<HTMLDivElement>(null);
  // A page with no build of its own, as in development, has nothing to offer, and no region.
  const [built] = useState(() => buildOf(document, page) !== null);
  if (!built) {
    return null;
  }
  return (
    <div
      // A polite live region, not a `status`, so the page's own statuses stay the only ones.
      aria-live="polite"
      ref={region}
      tabIndex={-1}
      className="pointer-events-none fixed inset-x-(--notice-inset) top-(--notice-top) z-50 outline-none"
    >
      {newer !== null && newer !== dismissed && (
        <NewVersion
          ui={ui}
          onDismiss={() => {
            // The button pressed goes with the offer: the region it was in keeps the focus.
            region.current?.focus();
            dismiss(newer);
          }}
        />
      )}
    </div>
  );
}
