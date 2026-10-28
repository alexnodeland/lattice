import { glyphs, IconButton, useCoarsePointer, useLoaded, useTouch } from "@portalr/ui";
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
 * A Mac, where Ctrl+K in a field is the system's: kill to the line's end. `navigator.platform` is
 * read in the browser alone, and says "MacIntel" on an iPad too, which has the same binding.
 */
const MAC = /Mac|iP(hone|ad|od)/.test(navigator.platform);

/**
 * Whether a key opens the palette (portalr ADR-0087): ⌘K anywhere, a field too; Ctrl+K outside a
 * field, and in one too but on a Mac, where it is the field's own; "/" outside a field. Never with
 * another modifier held, over a dialog or a menu already open, for a key already taken, or while an
 * input method composes.
 */
export function opensPalette(event: KeyboardEvent, mac = MAC): boolean {
  // A key a part has already taken, or one an input method is composing with, is theirs.
  if (event.defaultPrevented || event.isComposing) {
    return false;
  }
  const field =
    event.target instanceof Element &&
    event.target.closest(
      'input, textarea, select, [contenteditable]:not([contenteditable="false"])',
    ) !== null;
  const k =
    event.key.toLowerCase() === "k" &&
    !(event.altKey || event.shiftKey) &&
    (event.metaKey || (event.ctrlKey && !(mac && field)));
  const slash = event.key === "/" && !(event.metaKey || event.ctrlKey || event.altKey || field);
  return (
    (k || slash) &&
    document.querySelector('[role="dialog"], [role="alertdialog"], [role="menu"]') === null
  );
}

const Opening = createContext<{
  readonly open: (from: RefObject<HTMLElement | null>, docked?: boolean) => void;
  readonly icon: RefObject<HTMLButtonElement | null>;
  readonly shown: boolean;
} | null>(null);

/**
 * A workspace's search: the palette, opened by its magnifier on the bar, by a phone's tab bar,
 * whose whole bar it becomes (portalr ADR-0087), or by Ctrl+K, ⌘K or "/". Closed by Escape, the focus goes back to
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
  const [docked, setDocked] = useState(false);
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
        setDocked(false);
        setOpen(true);
      }
    };
    addEventListener("keydown", key);
    return () => removeEventListener("keydown", key);
  }, []);
  // Docked, it sits on the on-screen keyboard, as the composer's dock does: what the keyboard covers
  // is kept on the root while it is open, as iOS Safari resizes nothing of itself.
  const touch = useTouch(useCoarsePointer() && open && docked);
  useEffect(() => touch?.keyboardInset(), [touch]);
  // Docked in a phone's tab bar, it closes if the window stops being a phone's (turned, or widened).
  useEffect(() => {
    if (!(open && docked)) {
      return;
    }
    const phone = matchMedia("(max-width: 48rem) and (any-pointer: coarse)");
    const left = () => !phone.matches && setOpen(false);
    phone.addEventListener("change", left);
    return () => phone.removeEventListener("change", left);
  }, [open, docked]);
  const opening = {
    icon,
    shown: open,
    open: (from: RefObject<HTMLElement | null>, inBar = false) => {
      setBack(from);
      setDocked(inBar);
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
          docked={docked}
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

/**
 * The magnifier, which opens the palette: on the top bar, or, `docked`, at the end of a phone's
 * tab bar, which the palette's field then takes the place of.
 */
export function SearchButton({
  docked = false,
  className,
}: {
  docked?: boolean;
  className?: string;
}) {
  const opening = useContext(Opening);
  const own = useRef<HTMLButtonElement>(null);
  if (!opening) {
    return null;
  }
  const ref = docked ? own : opening.icon;
  return (
    <IconButton
      ref={ref}
      label="Search"
      icon={glyphs.search}
      aria-keyshortcuts="Control+K Meta+K /"
      aria-haspopup="dialog"
      aria-expanded={opening.shown}
      {...(className && { className })}
      onClick={() => opening.open(ref, docked)}
    />
  );
}
