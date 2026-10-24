import { expect, test } from "vitest";
import { committedOf } from "./canvas-host";

test("what a canvas's edit settles as is said in the kit's words, never the server's", () => {
  expect(committedOf({ outcome: "closed" }, 3)).toEqual({
    outcome: "refused",
    said: "The connection to the workspace closed.",
  });
  expect(
    committedOf({ outcome: "refused", result: { rejection: { type: "version_conflict" } } }, 3),
  ).toEqual({ outcome: "conflict" });
  const refused = committedOf(
    {
      outcome: "refused",
      result: { rejection: { type: "forbidden", message: "tenant t2's secret note" } },
    },
    3,
  );
  expect(refused).toEqual({ outcome: "refused", said: "You may not do this here." });
  const unknown = committedOf(
    { outcome: "refused", result: { rejection: { type: "odd", message: "internal: x" } } },
    3,
  );
  expect(unknown.outcome === "refused" && unknown.said).not.toMatch(/internal/);
  expect(committedOf({ outcome: "applied", result: { outcome: { type: "proposed" } } }, 3)).toEqual(
    { outcome: "proposed" },
  );
  expect(
    committedOf({ outcome: "applied", result: { outcome: { type: "applied", version: 7 } } }, 3),
  ).toEqual({ outcome: "applied", version: 7 });
  expect(committedOf({ outcome: "applied", result: {} }, 3)).toEqual({
    outcome: "applied",
    version: 4,
  });
});
