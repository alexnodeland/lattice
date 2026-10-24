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
import { Excalidraw, restoreElements } from "@excalidraw/excalidraw";
import type { ExcalidrawElement } from "@excalidraw/excalidraw/element/types";
import type {
  BinaryFileData,
  BinaryFiles,
  ExcalidrawImperativeAPI,
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
  type ReactNode,
  type RefObject,
  type SyntheticEvent,
  use,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { type CanvasHost, CanvasHostContext, useCanvasHost } from "./canvas-host";
import type { ElementJson, FileJson, Scene } from "./patch";
import { type Said, Saver } from "./saver";

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
      <Excalidraw
        excalidrawAPI={setApi}
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
