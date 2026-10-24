import type { Api } from "@portalr/client";
import { afterEach, expect, test, vi } from "vitest";
import { unmasked } from "../test/unmasked";
import {
  BATCH,
  BLOCKED,
  declarationsOk,
  MOST_BYTES,
  MOST_EVENTS,
  REGEXES,
  Recorder,
  scrub,
} from "./replay";

interface Posted {
  readonly tenant: string | undefined;
  readonly session: string;
  readonly events: Record<string, unknown>[];
}

/** A relay that signs "signed" and takes every batch, or refuses the first `refusals` with 403. */
function relay(refusals = 0) {
  const posted: Posted[] = [];
  let refused = 0;
  let signed = 0;
  const POST = vi.fn(
    async (path: string, init?: { headers?: Record<string, string>; body?: never }) => {
      if (path === "/portalr/v1/analytics/session") {
        signed += 1;
        return { data: { session: `signed-${signed}` }, response: { status: 200 } };
      }
      const body = init?.body as unknown as { session: string; events: Record<string, unknown>[] };
      if (refused < refusals) {
        refused += 1;
        return { data: undefined, response: { status: 403 } };
      }
      posted.push({ tenant: init?.headers?.["X-Tenant"], ...body });
      return { data: { recorded: body.events.length, dropped: 0 }, response: { status: 202 } };
    },
  );
  return { api: { portalr: { POST } } as unknown as Api, posted, POST };
}

const recorders: Recorder[] = [];
const recorder = (api: Api, wait = 20) => {
  const made = new Recorder(api, "acme", wait);
  recorders.push(made);
  return made;
};

afterEach(() => {
  for (const made of recorders.splice(0)) {
    made.close();
  }
  document.body.replaceChildren();
});

test("every value that may carry words is masked, and the page's own text and the mark stay", () => {
  const event = {
    type: 2,
    data: {
      node: {
        type: 0,
        childNodes: [
          { type: 1, name: "html", publicId: "", systemId: "" },
          { type: 3, textContent: "Launch on Tuesday" },
          { type: 3, textContent: ".a { color: red }", isStyle: true },
          { type: 3, textContent: "", isStyle: true },
          { type: 3, textContent: "SCRIPT_PLACEHOLDER" },
          {
            type: 2,
            tagName: "a",
            attributes: {
              href: "/t/acme/threads/thr_1",
              title: "alice@acme.com",
              "aria-label": "Open thread",
              "data-name": "Q3 plans",
              "data-portalr-replay": "block",
              class: "btn",
              width: 4,
              hidden: null,
            },
          },
        ],
      },
    },
  };
  const before = JSON.stringify(event);
  const scrubbedDoctype = scrub(event.data.node.childNodes[0]) as { name: string };
  const meta = { type: 4, data: { href: "http://acme.test/t/acme/w/notes", width: 800 } };
  const mutation = {
    type: 3,
    data: {
      source: 0,
      texts: [{ id: 1, value: "said it" }],
      attributes: [{ id: 2, attributes: { src: "/a.png" } }],
    },
  };
  const scrubbed = scrub([event, meta, mutation]);
  expect(JSON.stringify(event), "the event as recorded isn't changed").toBe(before);
  expect(scrubbedDoctype.name, "a player builds the document from its type's name").toBe("html");
  expect(() =>
    document.implementation.createDocumentType(scrubbedDoctype.name, "", ""),
  ).not.toThrow();
  expect(scrub({ type: 1, name: "Launch on Tuesday", publicId: "", systemId: "" })).toEqual({
    type: 1,
    name: "****** ** *******",
    publicId: "",
    systemId: "",
  });
  expect(scrub({ type: 2, name: "html", publicId: "", systemId: "" })).toEqual({
    type: 2,
    name: "****",
    publicId: "",
    systemId: "",
  });
  expect(unmasked(scrubbed)).toBeNull();
  const json = JSON.stringify(scrubbed);
  for (const word of [
    "Tuesday",
    "thr_1",
    "alice@acme.com",
    "Open thread",
    "Q3 plans",
    "said it",
    "a.png",
    "acme.test",
  ]) {
    expect(json, word).not.toContain(word);
  }
  expect(json, "a style element's text is not sent").not.toContain("color: red");
  expect(json).toContain("SCRIPT_PLACEHOLDER");
  expect(json).toContain('"data-portalr-replay":"block"');
  expect(json).toContain('"class":"btn"');
  expect(json).toContain('"width":4');
  expect(json).toContain('"hidden":null');
  expect(json, "a masked word keeps its length, and its spaces").toContain("*** **");
});

test("what rrweb records of a real page holds its layout and no word, input, address or blocked region", async () => {
  document.body.innerHTML = `
    <div id="page">
      <h1>Quarterly plan for Zebrafish</h1>
      <a id="open" href="/t/zebrafish/w/notes/threads/thr_777" title="Open thread: Walrus plans" aria-label="Walrus link">Walrus thread</a>
      <img alt="Narwhal portrait" src="https://avatars.test/narwhal.png">
      <input id="name" placeholder="Pelican name" value="">
      <textarea id="note"></textarea>
      <section data-portalr-replay="block"><p>Ostrich chat message</p></section>
      <div role="dialog"><p>Share with ocelot@zebrafish.test</p></div>
      <div role="alertdialog"><p>Revoke Lemur</p></div>
      <iframe srcdoc="<p>Hedgehog app</p>"></iframe>
      <div data-name="Badger" data-testid="Aardvark">layout</div>
    </div>`;
  const { api, posted } = relay();
  // A click that goes nowhere: the page under test stays where it is.
  document.querySelector("#open")?.addEventListener("click", (event) => event.preventDefault());
  recorder(api).start();
  const name = document.querySelector<HTMLInputElement>("#name");
  const note = document.querySelector<HTMLTextAreaElement>("#note");
  if (!name || !note) {
    throw new Error("the page isn't there");
  }
  name.value = "Capybara password";
  name.dispatchEvent(new Event("input", { bubbles: true }));
  note.value = "Platypus secret";
  note.dispatchEvent(new Event("input", { bubbles: true }));
  const added = document.createElement("p");
  added.textContent = "Quokka arrived";
  document.querySelector("#page")?.append(added);
  document.querySelector("#open")?.setAttribute("title", "Flamingo renamed");
  document.querySelector<HTMLElement>("#open")?.click();
  await expect
    .poll(() => posted.flatMap((batch) => batch.events).length, { timeout: 5_000 })
    .toBeGreaterThan(3);
  await new Promise((resolve) => setTimeout(resolve, 100));
  const events = posted.flatMap((batch) => batch.events);
  expect(posted.every((batch) => batch.tenant === "acme")).toBe(true);
  expect(events.map((event) => event.type)).toEqual(expect.arrayContaining([2, 4]));
  expect(unmasked(events)).toBeNull();
  const json = JSON.stringify(events);
  const words = [
    ...["Zebrafish", "Walrus", "Narwhal", "Pelican", "Ostrich", "ocelot", "Lemur", "Hedgehog"],
    ...[
      "Badger",
      "Aardvark",
      "Capybara",
      "Platypus",
      "Quokka",
      "Flamingo",
      "thr_777",
      "avatars.test",
    ],
  ];
  for (const word of words) {
    expect(json, word).not.toContain(word);
  }
  expect(json, "its layout is there").toContain('"id":"page"');
  expect(json, "and its document type, by which a player builds the document").toContain(
    '"name":"html"',
  );
  expect(json, "a click is there").toContain('"source":2');
});

test("a page's main is blocked unless the page marks itself, and recorded empty", async () => {
  document.body.innerHTML = `
    <main id="said"><p>Cormorant said it</p></main>`;
  const { api, posted } = relay();
  const made = recorder(api);
  made.start();
  await expect
    .poll(() => posted.flatMap((batch) => batch.events).length, { timeout: 5_000 })
    .toBeGreaterThan(0);
  const json = JSON.stringify(posted.flatMap((batch) => batch.events));
  expect(json).not.toContain("Cormorant");
  expect(json).not.toContain('"id":"said"');
  expect(json, "the box is there, its size").toContain("rr_width");
});

test("a main with a page that marks itself allow is recorded, its text masked", async () => {
  document.body.innerHTML = `
    <main id="listed"><div id="content"><i hidden data-portalr-replay="allow"></i><p>Cormorant said it</p></div></main>`;
  const { api, posted } = relay();
  recorder(api).start();
  await expect
    .poll(() => posted.flatMap((batch) => batch.events).length, { timeout: 5_000 })
    .toBeGreaterThan(0);
  const json = JSON.stringify(posted.flatMap((batch) => batch.events));
  expect(json).not.toContain("Cormorant");
  expect(json).toContain('"id":"listed"');
  expect(json).toContain('"data-portalr-replay":"allow"');
});

test("what the page blocks is an empty box, and the blocked selector names what a page marks, frames and dialogs", () => {
  document.body.innerHTML = `
    <section data-portalr-replay="block"></section><iframe></iframe><div role="dialog"></div>
    <div role="alertdialog"></div><div role="dialog"><div data-drawer=""></div></div><p></p>`;
  const blocked = [...document.querySelectorAll(BLOCKED)].map((each) => each.tagName.toLowerCase());
  expect(blocked).toEqual(["section", "iframe", "div", "div"]);
  document.body.innerHTML = '<main id="a"></main>';
  expect(document.querySelector("main")?.matches(BLOCKED)).toBe(true);
  document.body.innerHTML = '<main><div><i data-portalr-replay="allow"></i></div></main>';
  expect(document.querySelector("main")?.matches(BLOCKED)).toBe(false);
  document.body.innerHTML =
    '<main><div><section><i data-portalr-replay="allow"></i></section></div></main>';
  expect(document.querySelector("main")?.matches(BLOCKED), "a mark deeper opens nothing").toBe(
    true,
  );
  document.body.innerHTML = '<main><div><i data-portalr-replay="allow"></i></div></main>';
  expect(document.querySelector("main")?.matches(BLOCKED)).toBe(false);
});

test("events go in batches of a few, signed once, to the relay in the tenant", async () => {
  const { api, posted, POST } = relay();
  const made = recorder(api, 10_000);
  for (let n = 0; n < BATCH * 2 + 3; n += 1) {
    made.add({ type: 3, data: { source: 1, n } });
  }
  await expect.poll(() => posted.length).toBe(3);
  expect(posted.map((batch) => batch.events.length)).toEqual([BATCH, BATCH, 3]);
  expect(posted.every((batch) => batch.events.length <= MOST_EVENTS)).toBe(true);
  expect(new Set(posted.map((batch) => batch.session))).toEqual(new Set(["signed-1"]));
  expect(POST.mock.calls.filter(([path]) => path === "/portalr/v1/analytics/session")).toHaveLength(
    1,
  );
});

test("a few events wait a while, and are sent then", async () => {
  const { api, posted } = relay();
  recorder(api, 30).add({ type: 3, data: { source: 1 } });
  expect(posted).toEqual([]);
  await expect.poll(() => posted.length).toBe(1);
});

test("a batch over the relay's size is dropped, and the next goes", async () => {
  const { api, posted } = relay();
  const made = recorder(api, 10_000);
  made.add({ type: 3, data: { source: 5, text: "*".repeat(MOST_BYTES) } });
  await made.flush();
  made.add({ type: 3, data: { source: 3 } });
  await made.flush();
  expect(posted.map((batch) => batch.events.length)).toEqual([1]);
  expect(JSON.stringify(posted[0]?.events)).toContain('"source":3');
});

test("a session the relay no longer takes is signed afresh, once", async () => {
  const { api, posted, POST } = relay(1);
  const made = recorder(api, 10_000);
  made.add({ type: 3, data: { source: 1 } });
  await made.flush();
  expect(posted.map((batch) => batch.session)).toEqual(["signed-2"]);
  expect(POST.mock.calls.filter(([path]) => path === "/portalr/v1/analytics/session")).toHaveLength(
    2,
  );
});

test("a relay that fails drops the batch, and never fails the screen", async () => {
  const POST = vi.fn(async (path: string) => {
    if (path === "/portalr/v1/analytics/session") {
      return { data: { session: "signed" }, response: { status: 200 } };
    }
    throw new Error("network");
  });
  const made = recorder({ portalr: { POST } } as unknown as Api, 10_000);
  made.add({ type: 3, data: { source: 1 } });
  await expect(made.flush()).resolves.toBeUndefined();
  expect(POST).toHaveBeenCalledTimes(2);
});

test("a session that can't be signed sends nothing", async () => {
  const POST = vi.fn(async () => ({ data: undefined, response: { status: 503 } }));
  const made = recorder({ portalr: { POST } } as unknown as Api, 10_000);
  made.add({ type: 3, data: { source: 1 } });
  await made.flush();
  expect(POST).toHaveBeenCalledOnce();
});

test("closed, it drops what waits, records nothing more and sends nothing", async () => {
  document.body.innerHTML = "<main><p>Heron</p></main>";
  const { api, posted, POST } = relay();
  const made = recorder(api, 30);
  made.start();
  made.close();
  made.add({ type: 3, data: { source: 1 } });
  document.body.append(document.createElement("div"));
  await new Promise((resolve) => setTimeout(resolve, 200));
  expect(posted).toEqual([]);
  expect(POST).not.toHaveBeenCalled();
  await expect(made.flush()).resolves.toBeUndefined();
});

test("an identifier is one and a name is a name: what is neither is masked or goes", () => {
  const [kept] = scrub([
    {
      type: 2,
      attributes: {
        id: "Alice Smith",
        class: "user-alice-smith secret@acme",
        "alice-smith": true,
        "alice smith": "",
        for: "Alice Smith",
        "aria-labelledby": "a b",
        role: "menuitem",
        "data-portalr-replay": "walrus",
      },
    },
  ]) as [{ attributes: Record<string, unknown> }];
  expect(kept.attributes).toEqual({
    id: "***** *****",
    class: "**************** ***********",
    for: "***** *****",
    "aria-labelledby": "a b",
    role: "menuitem",
    "data-portalr-replay": "block",
  });
});

test("a key rrweb's events don't have goes, whatever it holds", () => {
  expect(scrub({ type: 3, sparkle: "walrus", data: { source: 1, "alice-smith": true } })).toEqual({
    type: 3,
    data: { source: 1 },
  });
});

test("changes to style and to a declaration are kept as rrweb makes them, unless they render text", () => {
  const style = { top: "0px", left: ["0px", "important"], right: false, content: '"walrus"' };
  const [changed] = scrub([{ data: { attributes: [{ id: 1, attributes: { style } }] } }]) as [
    { data: { attributes: [{ attributes: { style: Record<string, unknown> } }] } },
  ];
  expect(changed.data.attributes[0].attributes.style).toEqual({
    top: "0px",
    left: ["0px", "important"],
    right: false,
    content: "********",
  });
  expect(scrub({ data: { source: 13, set: { property: "top", value: "0px" } } })).toEqual({
    data: { source: 13, set: { property: "top", value: "0px" } },
  });
  expect(scrub({ data: { source: 13, set: { property: "top", value: '"walrus"' } } })).toEqual({
    data: { source: 13, set: { property: "top", value: "********" } },
  });
});

/** Milliseconds `work` takes, by `clock`, which a test may replace. */
function took(work: () => void, clock = () => performance.now()) {
  const started = clock();
  work();
  return clock() - started;
}

/**
 * The fastest of several runs, after one to warm up: a loaded runner makes a run slower, never
 * faster, so the minimum is the cost of the work and the rest is noise.
 */
function best(work: () => void, runs = 7, clock = () => performance.now()) {
  work();
  return Math.min(...Array.from({ length: runs }, () => took(work, clock)));
}

/**
 * Whether twice the input takes about twice the time. Linear doubles and a quadratic quadruples,
 * so three times the smaller (the fastest of several runs of each), and a floor above
 * what a timer and a collection can add, tell them apart.
 */
function scalesLinearly(
  work: (size: number) => void,
  small: number,
  large: number,
  runs = 7,
  clock = () => performance.now(),
) {
  const less = best(() => work(small), runs, clock);
  const more = best(() => work(large), runs, clock);
  return more < 3 * less + 10;
}

const UNITS = ["7", "a", " ", "-", ".", "/*", "url(", "x:", "'", '"', "\\", "px", "a b", "\n"];

test("the timing test tells a linear cost from a quadratic one, by a clock the test sets", () => {
  // Work that costs what its input says, on a clock that moves only by that: no real time, so
  // no runner can change the answer.
  let now = 0;
  const clock = () => now;
  const costing = (cost: (size: number) => number) => (size: number) => {
    now += cost(size);
  };
  const linear = costing((size) => size * 0.01);
  const quadratic = costing((size) => size * size * 0.000001);
  expect(scalesLinearly(linear, 8_000, 16_000, 3, clock)).toBe(true);
  expect(scalesLinearly(quadratic, 8_000, 16_000, 3, clock)).toBe(false);
  // The floor: work too quick to tell apart passes.
  expect(
    scalesLinearly(
      costing(() => 0.5),
      8_000,
      16_000,
      3,
      clock,
    ),
  ).toBe(true);
  // A noisy run is slower, never faster: the fastest of several is what counts.
  let slow = 0;
  const noisy = costing((size) => size * 0.01 + (slow++ % 3 === 0 ? 500 : 0));
  expect(scalesLinearly(noisy, 8_000, 16_000, 7, clock)).toBe(true);
});

test("every pattern is matched in time linear in what is matched: twice the input, about twice the time", {
  timeout: 120_000,
}, () => {
  for (const pattern of REGEXES) {
    for (const unit of UNITS) {
      const match = (size: number) => {
        const text = `${unit.repeat(size).slice(0, size)}!`;
        pattern.test(text);
        pattern.test(`!${text}`);
      };
      expect(scalesLinearly(match, 8_000, 16_000), `${pattern} on ${JSON.stringify(unit)}`).toBe(
        true,
      );
    }
  }
});

test("a hostile string costs no more than a plain one of the same length", {
  timeout: 60_000,
}, () => {
  const run = (unit: string) =>
    best(() => {
      const text = unit.repeat(20_000);
      const attributes = Object.fromEntries(
        ["width", "style", "class", "d", "id", "title", "rel"].map((name) => [name, text]),
      );
      scrub([{ type: 2, tagName: text, attributes, childNodes: [] }]);
      declarationsOk(text);
    });
  const plain = run("a");
  for (const unit of UNITS) {
    expect(run(unit), JSON.stringify(unit)).toBeLessThan(10 * plain + 100);
  }
});

test("a string is capped before any pattern is tried", () => {
  const [kept] = scrub([
    {
      type: 2,
      attributes: { width: "7".repeat(300), id: "a".repeat(300) },
      tagName: "d".repeat(300),
    },
  ]) as [{ attributes: Record<string, string>; tagName: string }];
  expect(kept.attributes.width).toBe("*".repeat(300));
  expect(kept.attributes.id).toBe("*".repeat(300));
  expect(kept.tagName).toBe("*".repeat(300));
});

test("a page's own stylesheet is named, not sent, and other CSS a page makes is left out", async () => {
  const linked = (href: string) => [
    {
      type: 2,
      tagName: "link",
      attributes: { rel: "stylesheet", href, _cssText: ".a{color:red}" },
    },
  ];
  const kept = (href: string) =>
    (scrub(linked(href)) as { attributes: Record<string, unknown> }[])[0]?.attributes;
  expect(kept("/portalr/app/assets/index-ab12.css")).toEqual({
    rel: "stylesheet",
    href: "*".repeat("/portalr/app/assets/index-ab12.css".length),
    rr_css: "index-ab12.css",
  });
  for (const elsewhere of [
    "https://cdn.test/index.css",
    "/portalr/app/assets/a b.css",
    "/portalr/app/assets/index.js",
    "/portalr/app/assets/x/..%2f.css",
    "/portalr/brand/kit.css",
    "/portalr/app/other/index-ab12.css",
  ]) {
    expect(kept(elsewhere)?.rr_css, elsewhere).toBeUndefined();
    expect(JSON.stringify(kept(elsewhere)), elsewhere).not.toContain("color");
  }
  const style = document.createElement("style");
  style.textContent = '.zz::after { content: "Launch on Tuesday" }';
  document.head.append(style);
  const { api, posted } = relay();
  recorder(api).start();
  await expect
    .poll(() => posted.flatMap((batch) => batch.events).length, { timeout: 5_000 })
    .toBeGreaterThan(1);
  const events = posted.flatMap((batch) => batch.events);
  style.remove();
  expect(JSON.stringify(events)).not.toContain("Tuesday");
  expect(unmasked(events)).toBeNull();
});

test("without :has() nothing is recorded, since nothing would be blocked", async () => {
  const supports = CSS.supports.bind(CSS);
  CSS.supports = (...given: [string]) =>
    given[0] === "selector(:has(*))" ? false : supports(...given);
  try {
    const { api, posted } = relay();
    recorder(api).start();
    await new Promise((resolve) => setTimeout(resolve, 300));
    expect(posted).toEqual([]);
  } finally {
    CSS.supports = supports;
  }
});

test("css a page makes is sent as a rule that does nothing, whatever its length, and a Kelvin sign is not a k", () => {
  const sent = scrub({
    data: { source: 8, replace: "a{color:red}".repeat(50), adds: [{ rule: "b{}" }] },
  });
  expect(sent).toEqual({ data: { source: 8, replace: "x{}", adds: [{ rule: "x{}" }] } });
  expect(declarationsOk("position: fixed")).toBe(true);
  expect(declarationsOk("position: fixeD".replace("D", "K"))).toBe(false);
  expect(declarationsOk("display: blocK")).toBe(false);
});
