import { expect, test } from "vitest";
import { elementsOf } from "./canvas";

test("the canvas takes no link, no embedded page and no image, and restores what it takes", () => {
  const taken = elementsOf({
    elements: {
      a: { id: "a", type: "rectangle", x: 0, y: 0, width: 10, height: 10, link: "https://x.test/" },
      e: { id: "e", type: "embeddable", link: "https://www.youtube.com/watch?v=x" },
      i: { id: "i", type: "iframe" },
      p: { id: "p", type: "image", fileId: "f" },
      bad: { id: "bad", type: "rectangle", x: "far", width: Number.NaN },
      pointless: { id: "pointless", type: "arrow", points: "none" },
      odd: 7,
      list: [],
    },
  });
  expect(taken.map((element) => [element.id, element.type, element.link])).toEqual([
    ["a", "rectangle", null],
    ["bad", "rectangle", null],
  ]);
  const arrow = taken.find((element) => element.id === "bad");
  expect(Number.isFinite(arrow?.x)).toBe(true);
  expect(elementsOf({ elements: "none" })).toEqual([]);
});
