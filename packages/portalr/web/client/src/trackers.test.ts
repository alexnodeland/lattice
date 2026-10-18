import { expect, test } from "vitest";
import type { Filed } from "./queries";
import { filedBy } from "./trackers";

const FILED: Filed = {
  tracker: "plane",
  items: [
    {
      key: "dead-letter/b",
      project: "p",
      id: "2",
      number: 13,
      name: "OPS-13",
      link: "https://plane.test/acme/browse/OPS-13/",
      deleted: true,
      chains: ["c2"],
    },
    {
      key: "dead-letter/a",
      project: "p",
      id: "1",
      number: 12,
      name: "OPS-12",
      link: "https://plane.test/acme/browse/OPS-12/",
      deleted: false,
      chains: ["c1", "c2"],
    },
  ],
};

test("a chain's items are those it filed or commented on, newest first", () => {
  expect(filedBy(FILED, "c2")).toEqual([
    {
      tracker: "plane",
      name: "OPS-13",
      link: "https://plane.test/acme/browse/OPS-13/",
      deleted: true,
    },
    {
      tracker: "plane",
      name: "OPS-12",
      link: "https://plane.test/acme/browse/OPS-12/",
      deleted: false,
    },
  ]);
  expect(filedBy(FILED, "c1").map((item) => item.name)).toEqual(["OPS-12"]);
  expect(filedBy(FILED, "c3")).toEqual([]);
});

test("no tracker, nothing read yet, or a run of no known chain files nothing", () => {
  expect(filedBy(null, "c1")).toEqual([]);
  expect(filedBy(undefined, "c1")).toEqual([]);
  expect(filedBy(FILED, "")).toEqual([]);
});
