import { createRef } from "react";
import { expect, test } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { CanvasDialog, elementsOf, kept } from "./canvas";

test("the canvas takes no link, no embedded page and no image, and restores what it takes", () => {
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
  expect(elements.map((element) => element.id).sort()).toEqual(
    ["box", "dangling", "orphan", "pointless"].filter((id) => elements.some((e) => e.id === id)),
  );
  expect(left).toBe(4 - elements.length);
  const field = (id: string, key: string) =>
    (elements.find((element) => element.id === id) as unknown as Record<string, unknown>)?.[key];
  expect(field("dangling", "startBinding") ?? null).toBeNull();
  expect(field("orphan", "containerId") ?? null).toBeNull();
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
    />,
  );
  await expect.poll(() => document.querySelector(".excalidraw canvas")).not.toBeNull();
  (document.querySelector(".excalidraw") as HTMLElement).focus();
  await userEvent.keyboard("?");
  await new Promise((settled) => setTimeout(settled, 300));
  expect(help()).toBeNull();
});
