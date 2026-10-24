/**
 * The canvas add-on (portalr ADR-0072, ADR-0074): Excalidraw, which draws a diagram in full, in a
 * chunk of its own, loaded only when someone opens a diagram's canvas. It opens to look at; a
 * person who may edit the diagram presses Edit, and what they draw is saved as their own edit,
 * through the workspace's stream (`saver.ts`).
 *
 * A diagram's elements are anyone's in the workspace to write, so the canvas takes only what it
 * draws: no link, and no embedded page; an image only where the diagram names its bytes, which
 * the canvas reads over the diagrams' routes; each element restored by Excalidraw as its own
 * canvas restores one, and a diagram it can't draw falls back to its text version. What it saves
 * holds no link, no embedded page and no image but one it uploaded, a PNG or a JPEG. What would
 * leave the canvas is refused at its edge: in view mode its shortcuts, a drop, a paste, its menus;
 * in edit mode its help, its command palette, a link, save and open, a drop of anything but an
 * image, and its context menu, whose items include a link.
 */

import "@excalidraw/excalidraw/index.css";
import "./canvas.css";
import {
  CaptureUpdateAction,
  Excalidraw,
  reconcileElements,
  restoreElements,
} from "@excalidraw/excalidraw";
import type { RemoteExcalidrawElement } from "@excalidraw/excalidraw/data/reconcile";
import type { ExcalidrawElement } from "@excalidraw/excalidraw/element/types";
import type {
  BinaryFileData,
  BinaryFiles,
  Collaborator,
  ExcalidrawImperativeAPI,
  SocketId,
} from "@excalidraw/excalidraw/types";
import { DIAGRAM_IMAGE_TYPES, imageRefusal } from "@portalr/client/diagrams";
import {
  type AppHost,
  Button,
  type Data,
  FailureAlert,
  type Shown,
  WholeDialog,
} from "@portalr/ui";
import {
  Component,
  type DragEvent,
  type KeyboardEvent,
  lazy,
  type ReactNode,
  type RefObject,
  Suspense,
  type SyntheticEvent,
  use,
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { type CanvasHost, CanvasHostContext, useCanvasHost } from "./canvas-host";
import type { ElementJson, FileJson, Scene } from "./patch";
import { type Ghost, ghostsNow, type Heard, type Presence } from "./presence";
import { type Said, Saver } from "./saver";

/** The pictures of what others draw, and Excalidraw's export they need: fetched once someone does. */
const Ghosts = lazy(() => import("./pictures/ghosts"));

declare global {
  interface Window {
    EXCALIDRAW_ASSET_PATH: string;
  }
}

// The faces are the app's own copy (excalidraw.ts), never a CDN's. Set as the add-on loads, after
// Excalidraw's module has run: it reads the path only as it loads a face, so it is in time.
window.EXCALIDRAW_ASSET_PATH = `${import.meta.env.BASE_URL}excalidraw/`;

/** The page's scheme, as ui's tokens follow it: a chosen one, or the system's. */
function scheme(): "light" | "dark" {
  const chosen = document.documentElement.dataset.theme;
  if (chosen === "light" || chosen === "dark") return chosen;
  return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function watchScheme(changed: () => void): () => void {
  const media = matchMedia("(prefers-color-scheme: dark)");
  const observer = new MutationObserver(changed);
  observer.observe(document.documentElement, { attributeFilter: ["data-theme"] });
  media.addEventListener("change", changed);
  return () => {
    observer.disconnect();
    media.removeEventListener("change", changed);
  };
}

/** What the canvas never draws, nor saves: a page embedded, which loads from away. */
const UNDRAWN = new Set(["embeddable", "iframe"]);

/** An image's digest, as a diagram names its bytes. */
const DIGEST = /^[0-9a-f]{64}$/;

/** Whether an element is drawn: not a page embedded, and an image only where `files` names it. */
const drawn = (element: Record<string, unknown>, files: Readonly<Record<string, unknown>>) =>
  !UNDRAWN.has(String(element.type)) &&
  (element.type !== "image" ||
    (typeof element.fileId === "string" && DIGEST.test(element.fileId) && element.fileId in files));

/** The numbers an element is drawn by, each finite and within reach, or left for restore to fill. */
const NUMBERS = [
  "x",
  "y",
  "width",
  "height",
  "angle",
  "fontSize",
  "strokeWidth",
  "opacity",
  "roughness",
];

/** How far from the origin a number the canvas draws by may be: further, and it is left out. */
const REACH = 1e9;

/** Lists an element holds, each a list or left for restore to fill. */
const LISTS = ["groupIds", "boundElements"];

/** Colours an element holds, each a string or left for restore to fill. */
const COLOURS = ["strokeColor", "backgroundColor"];

const finite = (value: unknown) => typeof value === "number" && Math.abs(value) <= REACH;

/** An element's numbers, lists, colours and points as drawn: one that isn't is dropped, for restore to fill. */
function drawable(element: Record<string, unknown>): Record<string, unknown> {
  const kept: Record<string, unknown> = { ...element, link: null };
  for (const key of NUMBERS) {
    if (key in kept && !finite(kept[key])) delete kept[key];
  }
  for (const key of LISTS) {
    if (key in kept && !Array.isArray(kept[key])) delete kept[key];
  }
  for (const key of COLOURS) {
    if (key in kept && typeof kept[key] !== "string") delete kept[key];
  }
  const points = kept.points;
  const pair = (point: unknown) =>
    Array.isArray(point) && point.length === 2 && point.every(finite);
  if ("points" in kept && !(Array.isArray(points) && points.every(pair))) delete kept.points;
  return kept;
}

/** What the canvas draws of a diagram, and how many of its live elements it leaves out. */
export interface Taken {
  readonly elements: ExcalidrawElement[];
  readonly left: number;
}

const isElement = (element: unknown): element is Record<string, unknown> =>
  typeof element === "object" && element !== null && !Array.isArray(element);

/**
 * A diagram's elements as the canvas takes them: objects only, none it doesn't draw, none with a
 * link, nothing it would draw by that isn't what it should be, each restored by Excalidraw, which
 * fills what one leaves out; and how many of the live ones are left out, which the canvas says.
 */
export function elementsOf(data: Data): Taken {
  const held = data.elements;
  if (!isElement(held)) return { elements: [], left: 0 };
  const files = isElement(data.files) ? data.files : {};
  const objects = Object.values(held).filter(isElement);
  const live = objects.filter((element) => !element.isDeleted).length;
  const taken = objects.filter((element) => drawn(element, files)).map(drawable);
  const restored = (some: readonly Record<string, unknown>[]) =>
    restoreElements(some as unknown as ExcalidrawElement[], null).map((each) => ({
      ...each,
      link: null,
    }));
  let elements: ExcalidrawElement[];
  try {
    // Together, so a label keeps its shape and an arrow what it binds.
    elements = restored(taken);
  } catch {
    // Excalidraw's restore throws on some it can't mend, such as an arrow with no points: then one
    // at a time, and each it can't is left out, not the whole diagram.
    elements = taken.flatMap((element) => {
      try {
        return restored([element]);
      } catch {
        return [];
      }
    });
  }
  const kept = new Set(elements.map((element) => element.id));
  const here = (binding: { elementId?: unknown } | null | undefined) =>
    binding && typeof binding.elementId === "string" && kept.has(binding.elementId)
      ? binding
      : null;
  // What an element binds to, or is held in, is let go where that isn't drawn.
  const bound = elements.map((element) => {
    const fields = element as unknown as Record<string, unknown>;
    const changed: Record<string, unknown> = {
      ...fields,
      boundElements: Array.isArray(fields.boundElements)
        ? fields.boundElements.filter((each: { id?: unknown }) => kept.has(String(each?.id)))
        : fields.boundElements,
    };
    if ("startBinding" in fields) changed.startBinding = here(fields.startBinding as never);
    if ("endBinding" in fields) changed.endBinding = here(fields.endBinding as never);
    if (typeof fields.containerId === "string" && !kept.has(fields.containerId)) {
      changed.containerId = null;
    }
    return changed as unknown as ExcalidrawElement;
  });
  return { elements: bound, left: live - bound.filter((element) => !element.isDeleted).length };
}

/** Zoom by the keyboard, which view mode keeps: Ctrl or ⌘ with +, - or 0. */
const ZOOM = new Set(["+", "=", "-", "_", "0"]);

/**
 * Keys the canvas may have: Tab and Escape, which the dialog keeps and closes by; the arrows;
 * Ctrl or ⌘ with +, - or 0, which zoom; the modifiers alone; and Enter and Space on a button, such
 * as its zoom buttons, unmodified. Any other, such as `?` for help, ⌘/ or ⌘K for the command
 * palette, ⌘S or ⌘O, never reaches Excalidraw, nor the browser's own save or open.
 */
export function kept(
  event: Pick<KeyboardEvent, "key" | "ctrlKey" | "metaKey" | "altKey" | "target">,
): boolean {
  if (event.key === "Tab" || event.key === "Escape" || event.key.startsWith("Arrow")) return true;
  const onButton =
    event.target instanceof Element && event.target.closest("button, [role=button]") !== null;
  if ((event.key === "Enter" || event.key === " ") && onButton) {
    return !event.ctrlKey && !event.metaKey && !event.altKey;
  }
  if (
    event.key === "Shift" ||
    event.key === "Control" ||
    event.key === "Meta" ||
    event.key === "Alt"
  ) {
    return true;
  }
  return (event.ctrlKey || event.metaKey) && !event.altKey && ZOOM.has(event.key);
}

/**
 * Keys the canvas may have while a person edits: every key but `?` for help, ⌘/ and Ctrl+/ for
 * the command palette, ⌘K for a link, ⌘S and ⌘O, which save and open files of the browser's,
 * and Ctrl+Shift+E, which exports. In a text being written, every key but those last two.
 */
export function keptEditing(
  event: Pick<KeyboardEvent, "key" | "ctrlKey" | "metaKey" | "altKey" | "shiftKey" | "target">,
): boolean {
  const command = event.ctrlKey || event.metaKey;
  const key = event.key.toLowerCase();
  if (command && (key === "s" || key === "o")) return false;
  if (command && event.shiftKey && key === "e") return false;
  const writing =
    event.target instanceof Element && event.target.closest("textarea, input") !== null;
  if (writing) return true;
  if (event.key === "?" || (event.altKey && key === "/")) return false;
  return !(command && (key === "/" || key === "k" || key === "p"));
}

/** Whether a drop holds only images the canvas takes. */
const images = (event: DragEvent) =>
  [...event.dataTransfer.items].every(
    (item) => item.kind === "file" && DIAGRAM_IMAGE_TYPES.includes(item.type),
  ) && event.dataTransfer.items.length > 0;

/** A blob as a `data:` URL, which Excalidraw draws an image from. */
const dataUrl = (blob: Blob) =>
  new Promise<string>((done, failed) => {
    const reader = new FileReader();
    reader.onload = () => done(String(reader.result));
    reader.onerror = () => failed(reader.error);
    reader.readAsDataURL(blob);
  });

/** The images a diagram names, read for the canvas: one it can't read is left a placeholder. */
async function filesOf(
  data: Data,
  fetched: (sha256: string) => Promise<Blob | null>,
): Promise<BinaryFiles> {
  const named = isElement(data.files) ? data.files : {};
  const read = await Promise.all(
    Object.entries(named)
      .filter(([digest]) => DIGEST.test(digest))
      .map(async ([digest, file]): Promise<BinaryFileData | null> => {
        const blob = await fetched(digest);
        const mimeType = (file as { media_type?: unknown }).media_type;
        if (blob === null || !DIAGRAM_IMAGE_TYPES.includes(String(mimeType))) return null;
        return {
          id: digest,
          dataURL: (await dataUrl(blob)) as BinaryFileData["dataURL"],
          mimeType: mimeType as BinaryFileData["mimeType"],
          created: 0,
        } as BinaryFileData;
      }),
  );
  return Object.fromEntries(read.filter((each) => each !== null).map((each) => [each.id, each]));
}

/**
 * The canvas's elements and images as a diagram holds them: JSON, no link, no embedded page, and
 * an image only where its bytes are the diagram's or uploaded here.
 */
function heldOf(
  some: readonly ExcalidrawElement[],
  files: Readonly<Record<string, FileJson>>,
): Record<string, ElementJson> {
  const elements: Record<string, ElementJson> = {};
  for (const element of some) {
    const plain = JSON.parse(JSON.stringify(element)) as Record<string, unknown>;
    if (!drawn(plain, files)) continue;
    elements[String(plain.id)] = { ...plain, link: null } as unknown as ElementJson;
  }
  return elements;
}

function sceneNow(api: ExcalidrawImperativeAPI, files: Readonly<Record<string, FileJson>>): Scene {
  return { elements: heldOf(api.getSceneElementsIncludingDeleted(), files), files };
}

/**
 * Elements moved onto a head after a conflict, taken as the canvas takes any diagram's: what it
 * draws of them, and the same as a diagram holds them. A peer's or an agent's link, embedded page,
 * image it has no bytes for, or number out of reach never reaches the scene.
 */
export function movedOnto(
  moved: Readonly<Record<string, ElementJson>>,
  files: Readonly<Record<string, FileJson>>,
): { drawn: ExcalidrawElement[]; held: Record<string, ElementJson> } {
  const { elements } = elementsOf({ elements: moved, files });
  return { drawn: elements, held: heldOf(elements, files) };
}

/** Whether pasted text is Excalidraw's clipboard, carrying images of its own. */
export function carriesFiles(text: string): boolean {
  try {
    const parsed = JSON.parse(text) as { type?: unknown; files?: unknown };
    return (
      typeof parsed === "object" &&
      parsed !== null &&
      typeof parsed.type === "string" &&
      parsed.type.startsWith("excalidraw") &&
      isElement(parsed.files) &&
      Object.keys(parsed.files).length > 0
    );
  } catch {
    return false;
  }
}

const refused = (event: SyntheticEvent) => {
  event.preventDefault();
  event.stopPropagation();
};

/** A diagram the canvas couldn't draw: why, and that its text version holds it. */
class Drawn extends Component<{ children: ReactNode }, { error: unknown }> {
  override state: { error: unknown } = { error: null };

  static getDerivedStateFromError(error: unknown) {
    return { error };
  }

  override render() {
    if (this.state.error === null) return this.props.children;
    return (
      <div className="flex flex-col items-start gap-2 p-4">
        <FailureAlert error={this.state.error} />
        <p className="text-muted text-sm">
          The canvas couldn't draw it: its text version holds it.
        </p>
      </div>
    );
  }
}

/** A diagram's elements and images, as a patch is made from them. */
function sceneOf(data: unknown): Scene {
  const held = isElement(data) ? data : {};
  return {
    elements: (isElement(held.elements) ? held.elements : {}) as Scene["elements"],
    files: (isElement(held.files) ? held.files : {}) as Scene["files"],
  };
}

/** What the canvas says of its saving, as it says it. */
function saidAs(said: Said): string | null {
  if (said === null) return null;
  if (said.state === "stopped") return said.text;
  return said.state === "saving" ? "Saving…" : "Saved";
}

/** How often comings and goings are said, at most. */
const SAID_EVERY = 2_000;

/**
 * Who came and who left, said for a screen reader: each change in who is here, gathered and
 * said at most every two seconds, so a busy diagram doesn't talk over the person.
 */
export function useComings(here: readonly string[]): { text: string; time: number } {
  // Counted, so a batch said twice running, the same words, is a new thing to say again.
  const [said, setSaid] = useState({ text: "", time: 0 });
  const before = useRef<readonly string[]>([]);
  const waiting = useRef<string[]>([]);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    const came = here.filter((name) => !before.current.includes(name));
    const went = before.current.filter((name) => !here.includes(name));
    before.current = here;
    waiting.current.push(...came.map((name) => `${name} is here.`));
    waiting.current.push(...went.map((name) => `${name} left.`));
    if (waiting.current.length === 0 || timer.current !== null) return;
    timer.current = setTimeout(() => {
      timer.current = null;
      const text = waiting.current.join(" ");
      setSaid((last) => ({ text, time: last.time + 1 }));
      waiting.current = [];
    }, SAID_EVERY);
  }, [here]);
  useEffect(
    () => () => {
      if (timer.current !== null) clearTimeout(timer.current);
    },
    [],
  );
  return said;
}

/** The chart theme's colours a peer is drawn in: Excalidraw's canvas takes no custom property. */
const HUES = ["--chart-1", "--chart-2", "--chart-3"] as const;

/**
 * The kit's chart colours as the browser computes them inside `within`: in its scheme, and in
 * colour-blind mode where `data-cvd` asks for it, as the kit's charts read them (portalr
 * ADR-0047). Read as peers are heard, so a change of scheme shows by the next frame.
 */
function chartColours(within: Element): string[] {
  const probe = document.createElement("span");
  within.append(probe);
  const colours = HUES.map((name) => {
    probe.style.color = `var(${name})`;
    return getComputedStyle(probe).color;
  });
  probe.remove();
  return colours;
}

/**
 * A peer's colour: one of the kit's chart colours, by the order the peer was first heard in,
 * so each keeps its own while it is here. Its name, beside its pointer and in "Here now", is
 * what tells peers apart; the colour only helps.
 */
function colourOf(
  order: readonly string[],
  peer: string,
  colours: readonly string[],
): { background: string; stroke: string } {
  const at = Math.max(0, order.indexOf(peer));
  const colour = colours[at % colours.length] ?? "currentColor";
  return { background: colour, stroke: colour };
}

/** Who a peer is, as the server stamped it: its name, or its id. */
function nameOf(actor: { readonly id?: string; readonly name?: string | null }): string {
  return actor.name || actor.id || "Someone";
}

/** How far from the origin, and how large, an element of a peer's picture may be. */
const GHOST_REACH = 100_000;
const GHOST_SIDE = 20_000;
/** The most points a line of it may have, and the largest stroke and type it is drawn in. */
const GHOST_POINTS = 1_000;
const GHOST_STROKE = 50;
const GHOST_FONT = 400;

/** A colour as a hex, `transparent`, or `rgb[a]()` or `hsl[a]()` of numbers alone. */
const PLAIN =
  /^(?:#[0-9a-f]{3,8}|transparent|(?:rgb|hsl)a?\( ?[\d.]+%?(?:[,\s/]{1,3}[\d.]+%?){2,3} ?\))$/i;

/** The longest colour a picture may hold: any plain one is shorter. */
const LONGEST = 64;

/**
 * A colour a picture may hold, or `fallback` for any other, such as a `url(...)`. Its length
 * is checked first, and the pattern has one way to read each run of spaces, so no string a peer
 * sends makes it read for long.
 */
const colour = (value: unknown, fallback: string) =>
  typeof value === "string" && value.length <= LONGEST && PLAIN.test(value) ? value : fallback;

/** A peer's `editing`, taken as the canvas takes any diagram's, with no image: what is drawn. */
export function editingOf(
  editing: readonly Readonly<Record<string, unknown>>[],
): ExcalidrawElement[] {
  const keyed = Object.fromEntries(
    editing.map((element, at) => [String(element.id ?? at), element]),
  );
  // Nothing larger than a canvas could hold: a picture of it would only stall the page.
  return elementsOf({ elements: keyed, files: {} })
    .elements.filter(
      (element) =>
        element.type !== "image" &&
        Math.abs(element.x) <= GHOST_REACH &&
        Math.abs(element.y) <= GHOST_REACH &&
        Math.abs(element.width) <= GHOST_SIDE &&
        Math.abs(element.height) <= GHOST_SIDE &&
        (!("points" in element) || element.points.length <= GHOST_POINTS),
    )
    .map((element) => {
      // A picture is an SVG, whose colours are attributes: only plain colours reach it.
      const plain: Record<string, unknown> = {
        ...element,
        strokeColor: colour(element.strokeColor, "#1e1e1e"),
        backgroundColor: colour(element.backgroundColor, "transparent"),
        strokeWidth: Math.min(element.strokeWidth, GHOST_STROKE),
      };
      if ("fontSize" in element) plain.fontSize = Math.min(element.fontSize, GHOST_FONT);
      return plain as unknown as ExcalidrawElement;
    });
}

function Canvas({
  data,
  describedBy,
  host,
  shown,
}: {
  data: Data;
  describedBy: string;
  host: CanvasHost | null;
  shown: Shown | null;
}) {
  const theme = useSyncExternalStore(watchScheme, scheme);
  const { elements, left } = useMemo(() => elementsOf(data), [data]);
  const [editing, setEditing] = useState(false);
  const section = useRef<HTMLElement>(null);
  const editingNow = useRef(editing);
  editingNow.current = editing;
  // Excalidraw listens for its command palette on the window, as keys go down, before any of the
  // page's own handlers: so the canvas's guard listens there too, first. A layout effect is set
  // before any of Excalidraw's effects, so its listener is the window's first.
  useLayoutEffect(() => {
    const guard = (event: globalThis.KeyboardEvent) => {
      const within = section.current?.closest("[role=dialog]") ?? section.current;
      if (!(event.target instanceof Node) || !within?.contains(event.target)) return;
      const keys = event as unknown as KeyboardEvent;
      if (!(editingNow.current ? keptEditing(keys) : kept(keys))) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    };
    window.addEventListener("keydown", guard, { capture: true });
    return () => window.removeEventListener("keydown", guard, { capture: true });
  }, []);
  const [said, setSaid] = useState<Said>(null);
  const [refusal, setRefusal] = useState<string | null>(null);
  // Excalidraw's API, once it has drawn: only then is there a scene to edit.
  const [api, setApi] = useState<ExcalidrawImperativeAPI | null>(null);
  // Whether the person may edit it, as their grants say: Edit is offered only where they may.
  const [mayEdit, setMayEdit] = useState(false);
  // Asked once for the diagram, not again as its page draws it anew with each event.
  const id = shown?.id ?? null;
  const archived = shown?.archived === true;
  useEffect(() => {
    if (host === null || id === null || archived) return;
    let current = true;
    host.mayEdit(id).then(
      (may) => current && setMayEdit(may),
      () => undefined,
    );
    return () => {
      current = false;
    };
  }, [host, id, archived]);
  // The version Excalidraw's scene was drawn from: the page may read a newer one while it is
  // open, which the scene doesn't hold, so an edit is of this one.
  const [openedAt] = useState(() => shown?.version ?? 0);
  // The newest revision drawn here: one the page reads later is merged in as it arrives.
  const mergedAt = useRef(openedAt);
  // Who else is here, and what they are changing, over the canvas's own connection.
  const presence = useRef<Presence | null>(null);
  const [heard, setHeard] = useState<Heard>({ peers: new Map(), rights: null });
  // Who is here, by name, and their comings and goings, said politely, at most every two seconds.
  const here = useMemo(
    () => [...new Set([...heard.peers.values()].map((peer) => nameOf(peer.actor)))],
    [heard],
  );
  const comings = useComings(here);
  const hereLabel = useId();
  // The order peers were first heard in, which their colours follow.
  const order = useRef<readonly string[]>([]);
  const [ghosts, setGhosts] = useState<ReadonlyMap<string, Ghost>>(new Map());
  useEffect(() => {
    if (host === null || id === null) return;
    const watched = host.presence(id, setHeard);
    presence.current = watched;
    // Here from the start, before the pointer moves: the others are told at once.
    watched?.say({ baseVersion: mergedAt.current, pointer: null, selection: [], editing: [] });
    return () => {
      watched?.close();
      presence.current = null;
    };
  }, [host, id]);
  const head = shown?.version ?? 0;
  useEffect(() => {
    if (api === null) return;
    for (const peer of heard.peers.keys()) {
      if (!order.current.includes(peer)) order.current = [...order.current, peer];
    }
    const colours = chartColours(section.current ?? document.documentElement);
    const collaborators = new Map<SocketId, Collaborator>();
    for (const peer of heard.peers.values()) {
      const pointer = peer.pointer;
      collaborators.set(
        // Excalidraw's brand on a collaborator's key: the peer's opaque id is one.
        peer.peer as SocketId,
        {
          id: peer.peer,
          username: nameOf(peer.actor),
          color: colourOf(order.current, peer.peer, colours),
          selectedElementIds: Object.fromEntries(
            (peer.selection ?? []).map((each) => [each, true] as const),
          ),
          ...(pointer
            ? {
                pointer: { x: pointer.x, y: pointer.y, tool: pointer.tool ?? "pointer" },
                button: pointer.button ?? "up",
              }
            : {}),
        },
      );
    }
    api.updateScene({ collaborators });
    setGhosts((kept) =>
      ghostsNow(
        kept,
        [...heard.peers.values()].map((peer) => ({
          peer: peer.peer,
          name: nameOf(peer.actor),
          baseVersion: peer.base_version,
          elements: editingOf((peer.editing ?? []) as Readonly<Record<string, unknown>>[]),
        })),
        head,
      ),
    );
  }, [api, heard, head]);
  // A revision someone else saved, as the page reads it: merged into the scene as Excalidraw's
  // own collaboration merges one, never into this person's undo, and what the next save is of.
  useEffect(() => {
    if (api === null || shown === null || shown.version <= mergedAt.current) return;
    mergedAt.current = shown.version;
    // This person's own save, read back: the scene holds it already.
    if (saver.current !== null && shown.version <= saver.current.version) return;
    const named = (isElement(data.files) ? data.files : {}) as Record<string, FileJson>;
    const added = Object.keys(named).filter((digest) => !(digest in files.current));
    files.current = { ...named, ...files.current };
    const remote = elementsOf({ ...data, files: files.current }).elements;
    const local = api.getSceneElementsIncludingDeleted();
    // Excalidraw's brand on elements from elsewhere: these are, taken as any diagram's.
    const elements = reconcileElements(
      local,
      remote as RemoteExcalidrawElement[],
      api.getAppState(),
    );
    api.updateScene({ elements, captureUpdate: CaptureUpdateAction.NEVER });
    if (added.length > 0 && host !== null) {
      void filesOf({ files: named }, (sha256) =>
        added.includes(sha256) ? host.read(shown.id, sha256) : Promise.resolve(null),
      ).then((read) => api.addFiles(Object.values(read)));
    }
    // As Excalidraw holds them once drawn, its own indices given: what the next save compares.
    saver.current?.merged(
      { version: shown.version, scene: sceneOf(data) },
      heldOf(api.getSceneElementsIncludingDeleted(), files.current),
    );
  }, [api, data, shown, host]);
  const saver = useRef<Saver | null>(null);
  const sceneVersion = useRef(0);
  // The scene as the canvas closed, as a diagram holds it, taken before Excalidraw lets it go:
  // what the last save sends. While the canvas is open, a save reads Excalidraw's own.
  const closed = useRef<Scene | null>(null);
  const reading = useRef<(() => Scene) | null>(null);
  // The images the diagram names, and those uploaded here since: what the canvas may save.
  const files = useRef<Record<string, FileJson>>(
    (isElement(data.files) ? data.files : {}) as Record<string, FileJson>,
  );
  // What Excalidraw opens on, its images read once: it reads its initial data only as it mounts.
  const [initial] = useState(() =>
    filesOf(data, (sha256) =>
      host === null || shown === null ? Promise.resolve(null) : host.read(shown.id, sha256),
    ).then((read) => ({ elements, files: read, scrollToContent: true })),
  );
  // Closed, the canvas sends what it holds that isn't saved yet. A layout effect's cleanup runs
  // before Excalidraw's own unmounts, so its scene is still there to read.
  useLayoutEffect(
    () => () => {
      if (reading.current !== null) closed.current = reading.current();
      saver.current?.close();
    },
    [],
  );

  function edit() {
    if (host === null || shown === null || api === null) return;
    const canvas = api;
    const diagram = shown.id;
    const drawn = canvas.getSceneElementsIncludingDeleted();
    sceneVersion.current = drawn.reduce((sum, element) => sum + element.version, drawn.length);
    reading.current = () => sceneNow(canvas, files.current);
    saver.current = new Saver(
      // What the canvas drew at first, restored as Excalidraw restores it: what the edit is of.
      { version: openedAt, scene: sceneNow(canvas, files.current) },
      {
        commit: (edit) => host.commit(diagram, edit),
        head: async () => {
          const head = await host.head(diagram);
          return head === null ? null : { version: head.version, scene: sceneOf(head.data) };
        },
      },
      () => closed.current ?? sceneNow(canvas, files.current),
      (now) => {
        setSaid(now);
        if (now?.state === "stopped") setEditing(false);
      },
      (moved, named) => {
        // The head's images too, a peer's or an agent's, so their elements are drawn: their
        // bytes are read as the canvas reads any diagram's.
        const added = Object.keys(named).filter((digest) => !(digest in files.current));
        files.current = { ...named, ...files.current };
        const { drawn: elements, held } = movedOnto(moved, files.current);
        canvas.updateScene({ elements });
        if (added.length > 0) {
          void filesOf({ files: named }, (sha256) =>
            added.includes(sha256) ? host.read(diagram, sha256) : Promise.resolve(null),
          ).then((read) => canvas.addFiles(Object.values(read)));
        }
        return held;
      },
    );
    setEditing(true);
  }

  async function upload(file: File): Promise<string> {
    setRefusal(null);
    // Checked before anything decodes it: a few bytes may say more pixels than any viewer holds.
    const said = await imageRefusal(file);
    if (said !== null) {
      setRefusal(said);
      throw new Error(said);
    }
    if (host === null || shown === null) throw new Error("This canvas only shows its diagram.");
    const sent = await host.upload(shown.id, file);
    if (sent.outcome !== "done") {
      const why = sent.reasons.join(" ") || "The image wasn't uploaded.";
      setRefusal(why);
      throw new Error(why);
    }
    files.current = { ...files.current, [sent.result.sha256]: sent.result };
    return sent.result.sha256;
  }

  // Saving stopped says why first; then an image refused; then how saving goes.
  const status = said?.state === "stopped" ? said.text : (refusal ?? saidAs(said));
  return (
    <section
      ref={section}
      className="absolute inset-0"
      aria-label="Canvas"
      aria-describedby={describedBy}
      onKeyDownCapture={(event) => (editing ? keptEditing(event) : kept(event)) || refused(event)}
      onKeyUpCapture={(event) => (editing ? keptEditing(event) : kept(event)) || refused(event)}
      onDragOverCapture={(event) => (editing && images(event)) || refused(event)}
      onDropCapture={(event) => (editing && images(event)) || refused(event)}
      onPasteCapture={(event) => {
        if (!editing) return refused(event);
        // Excalidraw's own clipboard carries its images' bytes, which would be drawn but never
        // saved: an image goes on a canvas as a file, uploaded.
        if (carriesFiles(event.clipboardData.getData("text/plain"))) {
          setRefusal("Paste an image itself: images copied from a canvas aren't taken.");
          refused(event);
        }
      }}
      onContextMenuCapture={refused}
    >
      <div className="absolute top-2 right-2 z-10 flex items-center gap-2">
        {/* Polite, as a status is, but not one: the canvas's status says how saving goes. */}
        <span aria-live="polite" className="sr-only">
          {/* A node of its own each time, so the same words said again are said again. */}
          <span key={comings.time}>{comings.text}</span>
        </span>
        {heard.peers.size > 0 && (
          <span id={hereLabel} className="sr-only">
            Here now:
          </span>
        )}
        {heard.peers.size > 0 && (
          <ul
            aria-labelledby={hereLabel}
            className="flex gap-2 rounded-(--input-radius) bg-surface px-2 py-1 text-muted text-xs"
          >
            {here.map((name) => (
              <li key={name}>{name}</li>
            ))}
          </ul>
        )}
        {(status !== null || left > 0) && (
          <p
            role="status"
            className="rounded-(--input-radius) bg-surface px-2 py-1 text-muted text-xs"
          >
            {status ??
              `${left} ${left === 1 ? "element" : "elements"} not drawn here: its text version lists all`}
          </p>
        )}
        {host !== null &&
          shown !== null &&
          api !== null &&
          mayEdit &&
          shown.archived !== true &&
          !editing &&
          said?.state !== "stopped" && (
            <Button variant="secondary" size="sm" onClick={edit}>
              Edit
            </Button>
          )}
      </div>
      {api !== null && ghosts.size > 0 && (
        <Suspense fallback={null}>
          <Ghosts api={api} ghosts={ghosts} />
        </Suspense>
      )}
      <Excalidraw
        excalidrawAPI={setApi}
        isCollaborating={heard.peers.size > 0}
        initialData={initial}
        viewModeEnabled={!editing}
        zenModeEnabled={!editing}
        langCode="en"
        theme={theme}
        detectScroll={false}
        handleKeyboardGlobally={false}
        validateEmbeddable={false}
        onLinkOpen={(_, event) => event.preventDefault()}
        generateIdForFile={upload}
        onChange={() => {
          // Excalidraw calls it on every update, a re-render among them: only a changed scene,
          // its elements' versions summed as Excalidraw's own scene version is, is an edit.
          if (!editing || api === null) return;
          const now = api.getSceneElementsIncludingDeleted();
          const drawn = now.reduce((sum, element) => sum + element.version, now.length);
          if (drawn === sceneVersion.current) return;
          sceneVersion.current = drawn;
          saver.current?.changed();
        }}
        onPointerUpdate={({ pointer, button }) => {
          if (api === null || presence.current === null) return;
          const state = api.getAppState();
          const selection = Object.keys(state.selectedElementIds);
          // What is changing now: what is being drawn, and, with the pointer down, what is
          // selected, as it moves; nothing while the person only looks.
          const changing =
            editing && button === "down"
              ? api
                  .getSceneElements()
                  .filter((element) => state.selectedElementIds[element.id] === true)
              : [];
          const drawing = editing && state.newElement ? [state.newElement] : [];
          presence.current.say({
            baseVersion: saver.current?.version ?? mergedAt.current,
            pointer: { ...pointer, button },
            selection,
            editing: [...drawing, ...changing],
          });
        }}
        onPointerUp={() => {
          if (editing) saver.current?.released();
        }}
        UIOptions={{
          canvasActions: {
            changeViewBackgroundColor: false,
            clearCanvas: false,
            export: false,
            loadScene: false,
            saveAsImage: false,
            saveToActiveFile: false,
            toggleTheme: false,
          },
          tools: { image: editing },
        }}
      />
    </section>
  );
}

/** The canvas on an app's page, with its route's host. */
function RouteCanvas({
  place,
  ...props
}: {
  data: Data;
  describedBy: string;
  shown: Shown;
  place: NonNullable<AppHost["place"]>;
}) {
  return <Canvas {...props} host={useCanvasHost(place)} />;
}

/**
 * The canvas over the page, in a dialog that fills the window, open from when it loads until it is
 * closed; focus goes back to `finalFocus`, the button that opened it.
 */
export function CanvasDialog({
  data,
  name,
  describedBy,
  finalFocus,
  onClose,
  shown,
  place,
}: {
  data: Data;
  name: string;
  describedBy: string;
  finalFocus: RefObject<HTMLElement | null>;
  onClose: () => void;
  /** The artifact shown, as its page says: which diagram, at which version, to edit. */
  shown: Shown | null;
  /** Where the page is, and as whom, as its app host says: without it, the canvas only shows. */
  place: AppHost["place"] | null;
}) {
  const host = use(CanvasHostContext);
  return (
    <WholeDialog
      open
      onOpenChange={(open) => open || onClose()}
      title={name}
      close="Close canvas"
      describedBy={describedBy}
      finalFocus={finalFocus}
    >
      <Drawn>
        {host === null && shown !== null && place ? (
          <RouteCanvas data={data} describedBy={describedBy} shown={shown} place={place} />
        ) : (
          <Canvas data={data} describedBy={describedBy} host={host} shown={shown} />
        )}
      </Drawn>
    </WholeDialog>
  );
}
