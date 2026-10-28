import { glyphs, IconButton, useLoaded } from "@portalr/ui";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useRouteContext } from "@tanstack/react-router";
import {
  createContext,
  type ReactNode,
  type RefObject,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { titlesOf } from "./titles";
import { useWorkspace } from "./workspace";

/** The palette, loaded the first time it is opened (portalr ADR-0087). */
const loadPalette = () => import("./on-demand/palette");

/**
 * Whether a key opens the palette: Ctrl+K or ⌘K anywhere, and "/" where it isn't typed into a
 * field; never with another modifier held, and never over a dialog already open (portalr ADR-0087).
 */
export function opensPalette(event: KeyboardEvent): boolean {
  const k =
    event.key.toLowerCase() === "k" &&
    (event.metaKey || event.ctrlKey) &&
    !(event.altKey || event.shiftKey);
  const slash =
    event.key === "/" &&
    !(event.metaKey || event.ctrlKey || event.altKey) &&
    !(
      event.target instanceof Element &&
      event.target.closest("input, textarea, select, [contenteditable]")
    );
  return (k || slash) && document.querySelector('[role="dialog"], [role="alertdialog"]') === null;
}

const Opening = createContext<{
  readonly open: (from: RefObject<HTMLElement | null>) => void;
  readonly icon: RefObject<HTMLButtonElement | null>;
} | null>(null);

/**
 * A workspace's search: the palette, opened by its magnifier on the bar, by another way in such
 * as a phone's bottom band, or by Ctrl+K, ⌘K or "/". Closed by Escape, the focus goes back to
 * what opened it, the magnifier for a key; following what it found goes to that page's heading
 * (portalr ADR-0068).
 */
export function SearchPalette({
  tenant,
  workspace,
  children,
}: {
  tenant: string;
  workspace: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const icon = useRef<HTMLButtonElement>(null);
  const [back, setBack] = useState<RefObject<HTMLElement | null>>(icon);
  const palette = useLoaded(loadPalette, open).module;
  const { queries } = useRouteContext({ from: "/_signed/t/$tenant/w/$workspace" });
  const navigate = useNavigate();
  const { state } = useWorkspace();
  // The artifacts' titles, as the Artifacts page reads them, read once the palette is opened.
  const { data: read } = useQuery({
    ...queries.artifactr.artifacts(tenant, workspace),
    enabled: open,
  });
  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if (opensPalette(event)) {
        event.preventDefault();
        setBack(icon);
        setOpen(true);
      }
    };
    addEventListener("keydown", key);
    return () => removeEventListener("keydown", key);
  }, []);
  const opening = {
    icon,
    open: (from: RefObject<HTMLElement | null>) => {
      setBack(from);
      setOpen(true);
    },
  };
  return (
    <Opening value={opening}>
      {children}
      {palette && (
        <palette.Palette
          open={open}
          onOpenChange={setOpen}
          finalFocus={back}
          workspace={workspace}
          state={state}
          titles={titlesOf(read)}
          base={`/t/${encodeURIComponent(tenant)}/w/${encodeURIComponent(workspace)}`}
          go={(to, hash) => void navigate({ to, ...(hash && { hash }) })}
        />
      )}
    </Opening>
  );
}

/** Opens the palette, the focus to come back to `from`; outside a workspace, nothing. */
export const useOpenSearch = () => useContext(Opening)?.open;

/** The magnifier on the bar, which opens the palette. */
export function SearchButton() {
  const opening = useContext(Opening);
  return (
    opening && (
      <IconButton
        ref={opening.icon}
        label="Search"
        icon={glyphs.search}
        aria-keyshortcuts="Control+K Meta+K /"
        onClick={() => opening.open(opening.icon)}
      />
    )
  );
}
