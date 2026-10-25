import { expect, test } from "vitest";
import type { CanvasEdit, Committed } from "./canvas-host";
import type { ElementJson, Scene } from "./patch";
import { type Clock, EVERY, MAX_ELEMENTS, QUIET, type Said, Saver, summary } from "./saver";

/** A clock the test moves: each timer runs when the time it waits for has come. */
function manual() {
  let now = 0;
  let timers: { at: number; then: () => void }[] = [];
  const clock: Clock = {
    now: () => now,
    after(ms, then) {
      const timer = { at: now + ms, then };
      timers.push(timer);
      return () => {
        timers = timers.filter((each) => each !== timer);
      };
    },
  };
  const advance = async (ms: number) => {
    now += ms;
    const due = timers.filter((timer) => timer.at <= now);
    timers = timers.filter((timer) => timer.at > now);
    for (const timer of due) timer.then();
    await new Promise((done) => setTimeout(done, 0));
  };
  return { clock, advance };
}

const rect = (id: string, version: number, x = 0): ElementJson => ({
  id,
  type: "rectangle",
  version,
  versionNonce: version * 7,
  x,
});

function harness(answers: Committed[], head: Scene | null = null) {
  const { clock, advance } = manual();
  let scene: Scene = { elements: { r1: rect("r1", 1) }, files: {} };
  const commits: CanvasEdit[] = [];
  const said: Said[] = [];
  const moved: Record<string, ElementJson>[] = [];
  const saver = new Saver(
    { version: 1, scene },
    {
      commit: async (edit) => {
        commits.push(edit);
        return answers.shift() ?? { outcome: "applied", version: edit.baseVersion + 1 };
      },
      head: async () => (head === null ? null : { version: 5, scene: head }),
    },
    () => scene,
    (now) => said.push(now),
    (elements) => {
      moved.push(elements);
      scene = { ...scene, elements };
      return elements;
    },
    clock,
  );
  const draw = (elements: Record<string, ElementJson>) => {
    scene = { ...scene, elements: { ...scene.elements, ...elements } };
    saver.changed();
  };
  return { saver, commits, said, moved, draw, advance };
}

test("an edit is sent after two seconds of quiet, and at once when the person lets go", async () => {
  const { saver, commits, draw, advance, said } = harness([]);
  draw({ r1: rect("r1", 2, 10) });
  await advance(QUIET - 1);
  expect(commits).toHaveLength(0);
  await advance(1);
  expect(commits.map((edit) => edit.baseVersion)).toEqual([1]);
  expect(said.at(-1)).toEqual({ state: "saved" });
  // Let go within five seconds of the last: it waits for the five.
  draw({ r1: rect("r1", 3, 20) });
  saver.released();
  await advance(1000);
  expect(commits).toHaveLength(1);
  await advance(EVERY);
  expect(commits.map((edit) => edit.baseVersion)).toEqual([1, 2]);
  expect(saver.version).toBe(3);
});

test("nothing changed is nothing sent, and it says so", async () => {
  const { saver, commits, advance, said } = harness([]);
  saver.changed();
  expect(said).toEqual([{ state: "saving" }]);
  await advance(QUIET);
  expect(commits).toEqual([]);
  expect(said).toEqual([{ state: "saving" }, { state: "saved" }]);
});

test("a proposed edit, or a refused one, stops the saving and says why", async () => {
  const proposed = harness([{ outcome: "proposed" }]);
  proposed.draw({ r1: rect("r1", 2) });
  await proposed.advance(QUIET);
  expect(proposed.said.at(-1)).toMatchObject({ state: "stopped", text: /proposed/ });
  proposed.draw({ r1: rect("r1", 3) });
  await proposed.advance(EVERY * 2);
  expect(proposed.commits).toHaveLength(1);
  const refused = harness([{ outcome: "refused", said: "you may not." }]);
  refused.draw({ r1: rect("r1", 2) });
  await refused.advance(QUIET);
  expect(refused.said.at(-1)).toEqual({ state: "stopped", text: "Not saved. you may not." });
});

test("a stale edit is moved onto the head and sent again, three times at most", async () => {
  const head: Scene = { elements: { r1: rect("r1", 1), r2: rect("r2", 4) }, files: {} };
  const { commits, moved, draw, advance, said } = harness([{ outcome: "conflict" }], head);
  draw({ r1: rect("r1", 2, 30) });
  await advance(QUIET);
  expect(commits.map((edit) => edit.baseVersion)).toEqual([1, 5]);
  expect(moved[0]?.r2).toEqual(head.elements.r2);
  expect(commits[1]?.ops.map((op) => op.path)).toEqual(["/elements/r1/version", "/elements/r1"]);
  expect(said.at(-1)).toEqual({ state: "saved" });
  // Moved four times over: kept here, still said as saving, and sent with the next revision.
  const busy = harness(
    Array.from({ length: 4 }, () => ({ outcome: "conflict" as const })),
    head,
  );
  busy.draw({ r1: rect("r1", 2, 30) });
  await busy.advance(QUIET);
  expect(busy.commits).toHaveLength(4);
  expect(busy.said.at(-1)).toEqual({ state: "saving" });
  busy.saver.merged({ version: 6, scene: head }, {});
  await busy.advance(EVERY);
  expect(busy.commits.at(-1)?.baseVersion).toBe(6);
  expect(busy.said.at(-1)).toEqual({ state: "saved" });
  const unread = harness([{ outcome: "conflict" }], null);
  unread.draw({ r1: rect("r1", 2, 30) });
  await unread.advance(QUIET);
  expect(unread.said.at(-1)).toMatchObject({ state: "stopped" });
});

test("a revision someone else saved is what the next save is an edit of", async () => {
  const { saver, commits, draw, advance } = harness([]);
  // Theirs: r1 moved to version 3. Drawn here as it is, it is not sent back.
  const theirs: Scene = { elements: { r1: rect("r1", 3, 40) }, files: {} };
  saver.merged({ version: 2, scene: theirs }, { r1: rect("r1", 3, 40) });
  expect(saver.version).toBe(2);
  saver.merged({ version: 1, scene: theirs }, {});
  expect(saver.version).toBe(2); // an older revision changes nothing
  draw({ r1: rect("r1", 3, 40), r2: rect("r2", 1) });
  await advance(QUIET);
  expect(commits.map((edit) => [edit.baseVersion, edit.ops.map((op) => op.path)])).toEqual([
    [2, ["/elements/r2"]],
  ]);
});

test("a diagram past its limits isn't sent", async () => {
  const { commits, draw, advance, said } = harness([]);
  draw(
    Object.fromEntries(
      Array.from({ length: MAX_ELEMENTS }, (_, at) => [`e${at}`, rect(`e${at}`, 1)]),
    ),
  );
  await advance(QUIET);
  expect(commits).toEqual([]);
  expect(said.at(-1)).toMatchObject({ state: "stopped", text: /at most 2000 elements/ });
});

test("a summary says how many elements changed, and the images added", () => {
  expect(
    summary([
      { op: "test", path: "/elements/a/version", value: 1 },
      { op: "replace", path: "/elements/a", value: {} },
      { op: "add", path: "/elements/b", value: {} },
      { op: "add", path: `/files/${"a".repeat(64)}`, value: {} },
    ]),
  ).toBe("2 elements changed on the canvas, 1 image added");
  expect(summary([{ op: "add", path: "/elements/b", value: {} }])).toBe(
    "1 element changed on the canvas",
  );
});

test("closing sends what isn't saved yet, whatever the cadence, and nothing after", async () => {
  const { saver, commits, draw, advance } = harness([]);
  draw({ r1: rect("r1", 2) });
  await advance(QUIET);
  draw({ r1: rect("r1", 3) });
  saver.close();
  await advance(0);
  expect(commits.map((edit) => edit.baseVersion)).toEqual([1, 2]);
  draw({ r1: rect("r1", 4) });
  await advance(EVERY * 2);
  expect(commits).toHaveLength(2);
  // Closed with nothing changed, nothing is sent.
  const quiet = harness([]);
  quiet.saver.close();
  await quiet.advance(0);
  expect(quiet.commits).toEqual([]);
});

test("a conflict as the canvas closes sends the edit moved onto the head, not what it last read", async () => {
  const { clock, advance } = manual();
  const base: Scene = { elements: { r1: rect("r1", 1), r2: rect("r2", 1) }, files: {} };
  // A peer moved r2 on; the canvas, closed, can only give what it held as it closed.
  const head: Scene = { elements: { r1: rect("r1", 1), r2: rect("r2", 4, 9) }, files: {} };
  const closed: Scene = { elements: { r1: rect("r1", 2, 30), r2: rect("r2", 1) }, files: {} };
  const commits: CanvasEdit[] = [];
  const answers: Committed[] = [{ outcome: "conflict" }];
  const saver = new Saver(
    { version: 1, scene: base },
    {
      commit: async (edit) => {
        commits.push(edit);
        return answers.shift() ?? { outcome: "applied", version: edit.baseVersion + 1 };
      },
      head: async () => ({ version: 5, scene: head }),
    },
    () => closed,
    () => undefined,
    (elements) => elements,
    clock,
  );
  saver.changed();
  saver.close();
  await advance(0);
  expect(commits.map((edit) => edit.baseVersion)).toEqual([1, 5]);
  // Only this person's r1 is sent again: the peer's r2 stays the head's, not reverted.
  expect(commits[1]?.ops.map((op) => op.path)).toEqual(["/elements/r1/version", "/elements/r1"]);
});

test("a send that fails is said, and leaves the saver able to stop", async () => {
  const { clock, advance } = manual();
  const said: Said[] = [];
  const scene: Scene = { elements: { r1: rect("r1", 1) }, files: {} };
  let now = scene;
  const saver = new Saver(
    { version: 1, scene },
    {
      commit: () => Promise.reject(new Error("gone")),
      head: () => Promise.reject(new Error("gone")),
    },
    () => now,
    (each) => said.push(each),
    (elements) => elements,
    clock,
  );
  now = { ...scene, elements: { r1: rect("r1", 2) } };
  saver.changed();
  await advance(QUIET);
  expect(said.at(-1)).toEqual({
    state: "stopped",
    text: "Not saved. The connection to the workspace closed.",
  });
});

test("after a conflict, what is sent is what the canvas drew, given the head's images too", async () => {
  const { clock, advance } = manual();
  const digest = "e".repeat(64);
  const image = { sha256: digest, size: 4, media_type: "image/png" };
  const base: Scene = { elements: { r1: rect("r1", 1) }, files: {} };
  const head: Scene = {
    elements: { r1: rect("r1", 1), p1: { ...rect("p1", 1), type: "image", fileId: digest } },
    files: { [digest]: image },
  };
  let now: Scene = { elements: { r1: rect("r1", 2, 30) }, files: {} };
  const commits: CanvasEdit[] = [];
  const given: Readonly<Record<string, unknown>>[] = [];
  const answers: Committed[] = [{ outcome: "conflict" }];
  const saver = new Saver(
    { version: 1, scene: base },
    {
      commit: async (edit) => {
        commits.push(edit);
        return answers.shift() ?? { outcome: "applied", version: edit.baseVersion + 1 };
      },
      head: async () => ({ version: 5, scene: head }),
    },
    () => now,
    () => undefined,
    (elements, files) => {
      given.push(files);
      // The canvas draws them as it takes any diagram: here, r1 moved back into reach.
      const drawn = { ...elements, r1: { ...(elements.r1 as ElementJson), x: 0, link: null } };
      now = { elements: drawn, files: now.files };
      return drawn;
    },
    clock,
  );
  saver.changed();
  await advance(QUIET);
  expect(given).toEqual([{ [digest]: image }]);
  const sent = commits[1]?.ops.find((op) => op.op === "replace");
  expect(sent?.value).toMatchObject({ id: "r1", x: 0, link: null });
});
