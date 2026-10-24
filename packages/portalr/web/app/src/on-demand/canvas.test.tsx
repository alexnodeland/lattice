import { createRef } from "react";
import { expect, test } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { CanvasDialog, carriesFiles, elementsOf, kept, keptEditing, movedOnto } from "./canvas";
import { type CanvasHost, CanvasHostContext } from "./canvas-host";

test("the canvas takes no link, no embedded page and no image it has no bytes for, and restores what it takes", () => {
  const { elements, left } = elementsOf({
    elements: {
      linked: {
        id: "linked",
        type: "rectangle",
        x: 0,
        y: 0,
        width: 10,
        height: 10,
        link: "https://x.test/",
      },
      e: { id: "e", type: "embeddable", link: "https://www.youtube.com/watch?v=x" },
      i: { id: "i", type: "iframe" },
      p: { id: "p", type: "image", fileId: "f" },
      unplaced: { id: "unplaced", type: "rectangle", x: "far", width: Number.NaN },
      far: { id: "far", type: "ellipse", x: 1e308, y: -1e12, width: 10, height: 10 },
      odd: { id: "odd", type: "diamond", groupIds: "g", boundElements: 3, strokeColor: 7 },
      gone: { id: "gone", type: "rectangle", isDeleted: true },
      number: 7,
      list: [],
    },
  });
  expect(elements.map((element) => [element.id, element.type, element.link])).toEqual([
    ["linked", "rectangle", null],
    ["unplaced", "rectangle", null],
    ["far", "ellipse", null],
    ["odd", "diamond", null],
    ["gone", "rectangle", null],
  ]);
  const at = (id: string) => elements.find((element) => element.id === id);
  expect([at("unplaced")?.x, at("far")?.x, at("far")?.y]).toEqual([0, 0, 0]);
  expect([at("odd")?.groupIds, at("odd")?.boundElements, typeof at("odd")?.strokeColor]).toEqual([
    [],
    [],
    "string",
  ]);
  // The page, the frame and the image are the live elements left out; the deleted one isn't counted.
  expect(left).toBe(3);
  expect(elementsOf({ elements: "none" })).toEqual({ elements: [], left: 0 });
});

test("what restore can't mend is left out alone, and a binding to nothing is let go", () => {
  const { elements, left } = elementsOf({
    elements: {
      box: { id: "box", type: "rectangle", x: 0, y: 0, width: 10, height: 10 },
      pointless: { id: "pointless", type: "arrow", points: "none" },
      dangling: {
        id: "dangling",
        type: "arrow",
        x: 0,
        y: 0,
        points: [
          [0, 0],
          [10, 0],
        ],
        startBinding: { elementId: "nobody", focus: 0, gap: 1 },
      },
      orphan: { id: "orphan", type: "text", text: "hi", containerId: "nobody" },
    },
  });
  // The arrow with no points is the one restore can't mend: it alone is left out.
  expect(elements.map((element) => element.id).sort()).toEqual(["box", "dangling", "orphan"]);
  expect(left).toBe(1);
  const field = (id: string, key: string) => {
    const element = elements.find((each) => each.id === id) as unknown as Record<string, unknown>;
    expect(element).toBeDefined();
    return element[key];
  };
  // Present, and let go of what they pointed at.
  expect(field("dangling", "startBinding")).toBeNull();
  expect(field("orphan", "containerId")).toBeNull();
});

test("Enter and Space reach a button, the canvas's zoom buttons among them, and no other place", () => {
  const button = document.createElement("button");
  const canvas = document.createElement("canvas");
  expect(
    kept({ key: "Enter", target: button, ctrlKey: false, metaKey: false, altKey: false }),
  ).toBe(true);
  expect(kept({ key: " ", target: button, ctrlKey: false, metaKey: false, altKey: false })).toBe(
    true,
  );
  expect(
    kept({ key: "Enter", target: canvas, ctrlKey: false, metaKey: false, altKey: false }),
  ).toBe(false);
  expect(kept({ key: "Enter", target: button, ctrlKey: true, metaKey: false, altKey: false })).toBe(
    false,
  );
  expect(kept({ key: "?", target: button, ctrlKey: false, metaKey: false, altKey: false })).toBe(
    false,
  );
  expect(kept({ key: "=", target: canvas, ctrlKey: true, metaKey: false, altKey: false })).toBe(
    true,
  );
});

test("a diagram the canvas can't read says so, in the dialog, with its text version", async () => {
  const unreadable = new Proxy(
    { name: "Unreadable" },
    {
      get(target, key) {
        if (key === "elements") throw new Error("these elements can't be read");
        return Reflect.get(target, key);
      },
    },
  );
  const screen = await render(
    <CanvasDialog
      data={unreadable}
      name="Unreadable"
      describedBy="nowhere"
      finalFocus={createRef()}
      onClose={() => undefined}
      shown={null}
      place={null}
    />,
  );
  await expect
    .element(screen.getByText("The canvas couldn't draw it: its text version holds it."))
    .toBeVisible();
});

test("the guard bites: a key that opens Excalidraw's help bare opens nothing on the canvas", async () => {
  const { Excalidraw } = await import("@excalidraw/excalidraw");
  const bare = await render(
    <div style={{ height: 500, width: 800 }}>
      <Excalidraw viewModeEnabled handleKeyboardGlobally={false} />
    </div>,
  );
  const help = () => document.querySelector(".HelpDialog");
  await expect.poll(() => document.querySelector(".excalidraw canvas")).not.toBeNull();
  (document.querySelector(".excalidraw") as HTMLElement).focus();
  await userEvent.keyboard("?");
  await expect.poll(help).not.toBeNull();
  await bare.unmount();
  await render(
    <CanvasDialog
      data={{ name: "Guarded", elements: {} }}
      name="Guarded"
      describedBy="nowhere"
      finalFocus={createRef()}
      onClose={() => undefined}
      shown={null}
      place={null}
    />,
  );
  await expect.poll(() => document.querySelector(".excalidraw canvas")).not.toBeNull();
  (document.querySelector(".excalidraw") as HTMLElement).focus();
  await userEvent.keyboard("?");
  await new Promise((settled) => setTimeout(settled, 300));
  expect(help()).toBeNull();
});

test("an image is drawn only where the diagram names its bytes, by a digest", () => {
  const digest = "b".repeat(64);
  const { elements, left } = elementsOf({
    elements: {
      named: { id: "named", type: "image", fileId: digest, x: 0, y: 0, width: 4, height: 4 },
      unnamed: { id: "unnamed", type: "image", fileId: "c".repeat(64) },
      away: { id: "away", type: "image", fileId: "https://x.test/a.png" },
    },
    files: { [digest]: { sha256: digest, size: 4, media_type: "image/png" } },
  });
  expect(elements.map((element) => element.id)).toEqual(["named"]);
  expect(left).toBe(2);
});

test("while editing, every key reaches the canvas but help, the palette, a link, save, open and export", () => {
  const key = (
    key: string,
    more: Partial<Pick<KeyboardEvent, "ctrlKey" | "metaKey" | "altKey" | "shiftKey">> = {},
    target: EventTarget = document.body,
  ) =>
    keptEditing({
      key,
      ctrlKey: false,
      metaKey: false,
      altKey: false,
      shiftKey: false,
      target,
      ...more,
    });
  for (const each of ["r", "Delete", "z", "ArrowLeft", "Escape", "1", "t"]) {
    expect(key(each)).toBe(true);
  }
  expect(key("z", { ctrlKey: true })).toBe(true);
  expect(key("?")).toBe(false);
  expect(key("/", { ctrlKey: true })).toBe(false);
  expect(key("/", { metaKey: true })).toBe(false);
  expect(key("/", { altKey: true })).toBe(false);
  expect(key("k", { metaKey: true })).toBe(false);
  expect(key("P", { ctrlKey: true, shiftKey: true })).toBe(false);
  expect(key("s", { ctrlKey: true })).toBe(false);
  expect(key("o", { metaKey: true })).toBe(false);
  expect(key("E", { ctrlKey: true, shiftKey: true })).toBe(false);
  // In a text being written, `?` and ⌘K are text; save and open are still refused.
  const writing = document.createElement("textarea");
  expect(key("?", {}, writing)).toBe(true);
  expect(key("k", { metaKey: true }, writing)).toBe(true);
  expect(key("s", { metaKey: true }, writing)).toBe(false);
});

test("elements moved onto a head after a conflict are taken as the canvas takes any diagram's", () => {
  const digest = "d".repeat(64);
  const files = { [digest]: { sha256: digest, size: 4, media_type: "image/png" } };
  const at = (id: string, more: Record<string, unknown>) => ({
    id,
    version: 2,
    versionNonce: 3,
    x: 0,
    y: 0,
    width: 10,
    height: 10,
    ...more,
  });
  const { drawn, held } = movedOnto(
    {
      linked: at("linked", { type: "rectangle", link: "https://x.test/" }),
      page: at("page", { type: "embeddable", link: "https://www.youtube.com/watch?v=x" }),
      frame: at("frame", { type: "iframe" }),
      foreign: at("foreign", { type: "image", fileId: "https://x.test/a.png" }),
      far: at("far", { type: "ellipse", x: Number.NaN, y: 1e308 }),
      picture: at("picture", { type: "image", fileId: digest }),
    },
    files,
  );
  expect(drawn.map((element) => element.id).sort()).toEqual(["far", "linked", "picture"]);
  expect(drawn.every((element) => element.link === null)).toBe(true);
  const far = drawn.find((element) => element.id === "far");
  expect([far?.x, far?.y]).toEqual([0, 0]);
  expect(Object.keys(held).sort()).toEqual(["far", "linked", "picture"]);
  expect(held.linked?.link).toBeNull();
});

/** A host that may edit, and keeps nothing: the guard is what is tested. */
const editing: CanvasHost = {
  commit: async (_, edit) => ({ outcome: "applied", version: edit.baseVersion + 1 }),
  head: async () => null,
  upload: async () => ({ outcome: "refused", status: 0, reasons: ["no"] }),
  read: async () => null,
  mayEdit: async () => true,
};

test("the guard bites while editing: help and the palette open bare, and nothing on the canvas", async () => {
  const { Excalidraw } = await import("@excalidraw/excalidraw");
  const bare = await render(
    <div style={{ height: 500, width: 800 }}>
      <Excalidraw handleKeyboardGlobally={false} />
    </div>,
  );
  const opened = () => document.querySelector(".HelpDialog, .command-palette-dialog");
  await expect.poll(() => document.querySelector(".excalidraw canvas")).not.toBeNull();
  const focus = () => (document.querySelector(".excalidraw") as HTMLElement).focus();
  focus();
  await userEvent.keyboard("?");
  await expect.poll(() => document.querySelector(".HelpDialog")).not.toBeNull();
  await userEvent.keyboard("{Escape}");
  await expect.poll(opened).toBeNull();
  // The palette, by Ctrl+/ or ⌘/: Excalidraw 0.18.1 mounts it only for a host that renders its
  // <CommandPalette />, which the canvas doesn't, so bare it opens nothing either. A version that
  // mounts it by default fails here, and the canvas's window guard is then what keeps it shut.
  focus();
  await userEvent.keyboard("{Control>}/{/Control}");
  focus();
  await userEvent.keyboard("{Meta>}/{/Meta}");
  await new Promise((settled) => setTimeout(settled, 300));
  expect(document.querySelector(".command-palette-dialog")).toBeNull();
  // `0` takes the eraser, bare too, and opens no sidebar: it isn't the library's.
  focus();
  await userEvent.keyboard("0");
  await new Promise((settled) => setTimeout(settled, 300));
  expect(document.querySelector(".sidebar")).toBeNull();
  await bare.unmount();
  const screen = await render(
    <CanvasHostContext value={editing}>
      <CanvasDialog
        data={{ name: "Guarded", elements: {} }}
        name="Guarded"
        describedBy="nowhere"
        finalFocus={createRef()}
        onClose={() => undefined}
        shown={{ id: "d1", version: 1 }}
        place={null}
      />
    </CanvasHostContext>,
  );
  await screen.getByRole("button", { name: "Edit" }).click();
  await expect.poll(() => document.querySelector(".App-toolbar")).not.toBeNull();
  // What editing hides is there to hide: a version that renames it fails here.
  for (const hidden of [".default-sidebar-trigger", ".App-toolbar__extra-tools-trigger"]) {
    const found = document.querySelector(hidden);
    expect(found, hidden).not.toBeNull();
    expect(getComputedStyle(found as Element).display, hidden).toBe("none");
  }
  (document.querySelector(".excalidraw") as HTMLElement).focus();
  for (const keys of ["?", "{Control>}/{/Control}", "{Meta>}/{/Meta}", "0"]) {
    await userEvent.keyboard(keys);
  }
  await new Promise((settled) => setTimeout(settled, 300));
  expect(opened()).toBeNull();
  // `0` is the eraser's, not the library's: no sidebar opens.
  expect(document.querySelector(".sidebar")).toBeNull();
});

test("the person's grants are asked once for the diagram, however often its page draws it", async () => {
  let asked = 0;
  const counting: CanvasHost = {
    ...editing,
    mayEdit: async () => {
      asked += 1;
      return false;
    },
  };
  const dialog = (version: number) => (
    <CanvasHostContext value={counting}>
      <CanvasDialog
        data={{ name: "Asked", elements: {} }}
        name="Asked"
        describedBy="nowhere"
        finalFocus={createRef()}
        onClose={() => undefined}
        shown={{ id: "d1", version }}
        place={null}
      />
    </CanvasHostContext>
  );
  const screen = await render(dialog(1));
  await expect.poll(() => asked).toBe(1);
  for (const version of [1, 2, 3]) await screen.rerender(dialog(version));
  await new Promise((settled) => setTimeout(settled, 200));
  expect(asked).toBe(1);
  expect(screen.container.querySelector("button")?.textContent).not.toBe("Edit");
});

test("Excalidraw's own clipboard, carrying images, is refused; anything else isn't", () => {
  const copied = JSON.stringify({
    type: "excalidraw/clipboard",
    elements: [],
    files: { x: { dataURL: "data:image/png;base64,AA==" } },
  });
  expect(carriesFiles(copied)).toBe(true);
  expect(carriesFiles(JSON.stringify({ type: "excalidraw/clipboard", elements: [] }))).toBe(false);
  expect(carriesFiles("https://x.test/")).toBe(false);
  expect(carriesFiles("null")).toBe(false);
});
