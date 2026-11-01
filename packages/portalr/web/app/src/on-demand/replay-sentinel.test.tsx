/**
 * A word stamped into every attribute a page may carry, and into every other place text can hide,
 * must reach no batch the recorder sends. The list is written apart from the allow-list the
 * recorder reads: every HTML, ARIA and SVG attribute as the standards name them, and handlers.
 */

import type { Api } from "@portalr/client";
import { afterEach, expect, test } from "vitest";
import { unmasked } from "../test/unmasked";
import { Recorder } from "./replay";

const ATTRIBUTES = [
  ...new Set(
    `
  accept accept-charset accesskey action align allow
  allowfullscreen alt as async autocapitalize autocomplete
  autofocus autoplay background bgcolor border capture
  challenge charset checked cite class color
  cols colspan content contenteditable controls coords
  crossorigin data data-name data-testid data-x datetime
  decoding default defer dir dirname disabled
  download draggable enctype enterkeyhint for form
  formaction formenctype formmethod formnovalidate formtarget headers
  height hidden high href hreflang http-equiv
  id imagesizes imagesrcset inert inputmode integrity
  is ismap itemid itemprop itemref itemscope
  itemtype kind label lang list loading
  loop low manifest max maxlength media
  method min minlength multiple muted name
  nomodule nonce novalidate open optimum pattern
  ping placeholder playsinline poster preload radiogroup
  readonly referrerpolicy rel required rev reversed
  role rows rowspan sandbox scope scoped
  selected shape size sizes slot span
  spellcheck src srcdoc srclang srcset start
  step style summary tabindex target title
  translate type usemap value width wrap
  onclick onerror onload onmouseover oninput onchange
  onfocus onsubmit aria-activedescendant aria-atomic aria-autocomplete aria-braillelabel
  aria-brailleroledescription aria-busy aria-checked aria-colcount aria-colindex aria-colspan
  aria-controls aria-current aria-describedby aria-description aria-details aria-disabled
  aria-dropeffect aria-errormessage aria-expanded aria-flowto aria-grabbed aria-haspopup
  aria-hidden aria-invalid aria-keyshortcuts aria-label aria-labelledby aria-level
  aria-live aria-modal aria-multiline aria-multiselectable aria-orientation aria-owns
  aria-placeholder aria-posinset aria-pressed aria-readonly aria-relevant aria-required
  aria-roledescription aria-rowcount aria-rowindex aria-rowspan aria-selected aria-setsize
  aria-sort aria-valuemax aria-valuemin aria-valuenow aria-valuetext accent-height
  alignment-baseline clip-path clip-rule cx cy d
  direction dominant-baseline dx dy fill fill-opacity
  fill-rule filter flood-color font-family font-size font-weight
  fx fy gradientTransform gradientUnits image-rendering lengthAdjust
  letter-spacing marker-end marker-mid marker-start mask offset
  opacity orient overflow paint-order pathLength patternUnits
  points preserveAspectRatio r refX refY rx
  ry spreadMethod startOffset stop-color stop-opacity stroke
  stroke-dasharray stroke-dashoffset stroke-linecap stroke-linejoin stroke-miterlimit stroke-opacity
  stroke-width text-anchor text-decoration textLength transform vector-effect
  version viewBox visibility word-spacing writing-mode x
  x1 x2 xlink:actuate xlink:arcrole xlink:href xlink:role
  xlink:show xlink:title xlink:type xml:lang xml:space xmlns
  xmlns:xlink y y1 y2 z _cssText
  rr_dataURL rr_mediaState rr_scrollLeft rr_scrollTop rr_width rr_height
  focusable
`
      .split(/\s+/)
      .filter(Boolean),
  ),
];

const SENTINEL = 'Zq7 "walrus" said @alice';

const recorders: Recorder[] = [];
afterEach(() => {
  for (const made of recorders.splice(0)) {
    made.close();
  }
  document.body.replaceChildren();
});

test("a sentence stamped into any attribute, a stylesheet, an svg text, a shadow root or an editable reaches no batch", async () => {
  const page = document.createElement("div");
  page.id = "stamped";
  for (const name of ATTRIBUTES) {
    const each = document.createElement("div");
    each.setAttribute(name, SENTINEL);
    page.append(each);
  }
  page.insertAdjacentHTML(
    "beforeend",
    `
    <style>.walrus::after { content: "walrus said it"; } .b { background: url("https://x.test/walrus.png") }</style>
    <div style='content: "walrus"; background: url(https://x.test/walrus.png)'>styled walrus</div>
    <svg viewBox="0 0 10 10"><text x="1" y="2">walrus text</text><use xlink:href="#walrus"></use><title>walrus title</title></svg>
    <div contenteditable="true">walrus edits</div>
    <select><option value="walrus" label="walrus">walrus option</option></select>
    <textarea>walrus area</textarea><input value="walrus" placeholder="walrus" list="walrus">
    <noscript>walrus noscript</noscript><template><p>walrus template</p></template>
    <a href="https://x.test/walrus?name=alice" title="walrus">walrus link</a>
    <img alt="walrus" src="https://x.test/walrus.png" srcset="https://x.test/walrus.png 2x">
    <object data="https://x.test/walrus.pdf"></object><video poster="https://x.test/walrus.png"></video>
    `,
  );
  const host = document.createElement("div");
  host.attachShadow({ mode: "open" }).innerHTML = "<p title='walrus'>walrus shadow</p>";
  page.append(host);
  document.body.append(page);
  const meta = document.createElement("meta");
  meta.name = "description";
  meta.content = "walrus described";
  document.head.append(meta);
  document.title = "walrus titled";

  const posted: unknown[] = [];
  const api = {
    portalr: {
      POST: async (_command: null, path: string, init?: { body?: { events: unknown[] } }) => {
        if (path === "/portalr/v1/analytics/session") {
          return { data: { session: "s" }, response: { status: 200 } };
        }
        posted.push(...(init?.body?.events ?? []));
        return { data: { recorded: 1, dropped: 0 }, response: { status: 202 } };
      },
    },
  } as unknown as Api;
  const made = new Recorder(api, "acme", 20);
  recorders.push(made);
  made.start();
  const added = document.createElement("p");
  added.setAttribute("title", SENTINEL);
  added.textContent = "walrus added";
  page.append(added);
  page.firstElementChild?.setAttribute("aria-label", SENTINEL);
  await expect.poll(() => posted.length, { timeout: 5_000 }).toBeGreaterThan(2);
  await new Promise((resolve) => setTimeout(resolve, 200));
  meta.remove();
  const json = JSON.stringify(posted);
  expect(json).toContain('"id":"stamped"');
  expect(json).not.toMatch(/walrus|alice|Zq7/);
  expect(unmasked(posted)).toBeNull();
});

/**
 * What takes a bare word, written apart from the allow-list: the names of things the page's code
 * gives (an id, a class, a role, a relation) and the enumerations (a state, a boolean, a line end,
 * a colour keyword). Nothing else takes a plain word.
 */
const TAKES_A_WORD = new Set(
  `class id role type lang dir target for form headers inputmode disabled checked
  hidden open readonly required multiple selected draggable contenteditable focusable
  stroke-linecap stroke-linejoin fill-rule clip-rule
  async autofocus autoplay controls crossorigin decoding default defer enterkeyhint formnovalidate inert ismap
  loading loop muted nomodule novalidate playsinline popover preload reversed scope spellcheck translate wrap fetchpriority
  aria-expanded aria-hidden aria-checked aria-selected aria-pressed aria-disabled aria-current
  aria-haspopup aria-live aria-busy aria-modal aria-orientation aria-sort aria-atomic
  aria-multiselectable aria-required aria-readonly aria-invalid aria-autocomplete
  aria-labelledby aria-describedby aria-controls aria-owns aria-activedescendant`.split(/\s+/),
);

/** Every attribute map in the events, in snapshots and in mutations. */
function attributeMaps(value: unknown, found: Record<string, unknown>[] = []) {
  if (Array.isArray(value)) {
    for (const item of value) {
      attributeMaps(item, found);
    }
  } else if (value !== null && typeof value === "object") {
    for (const [key, item] of Object.entries(value)) {
      if (
        key === "attributes" &&
        item !== null &&
        typeof item === "object" &&
        !Array.isArray(item)
      ) {
        found.push(item as Record<string, unknown>);
      }
      attributeMaps(item, found);
    }
  }
  return found;
}

test("a bare word stamped into each attribute is kept in exactly those that name or enumerate things", async () => {
  const page = document.createElement("div");
  page.id = "bare";
  for (const name of ATTRIBUTES) {
    const each = document.createElement("div");
    each.setAttribute(name, "walrus");
    page.append(each);
  }
  document.body.append(page);
  const posted: unknown[] = [];
  const api = {
    portalr: {
      POST: async (_command: null, path: string, init?: { body?: { events: unknown[] } }) => {
        if (path === "/portalr/v1/analytics/session") {
          return { data: { session: "s" }, response: { status: 200 } };
        }
        posted.push(...(init?.body?.events ?? []));
        return { data: { recorded: 1, dropped: 0 }, response: { status: 202 } };
      },
    },
  } as unknown as Api;
  const made = new Recorder(api, "acme", 20);
  recorders.push(made);
  made.start();
  await expect.poll(() => posted.length, { timeout: 5_000 }).toBeGreaterThan(1);
  await new Promise((resolve) => setTimeout(resolve, 200));
  const kept = new Set(
    attributeMaps(posted).flatMap((map) =>
      Object.entries(map)
        .filter(([, value]) => value === "walrus")
        .map(([name]) => name),
    ),
  );
  const expected = new Set(ATTRIBUTES.filter((name) => TAKES_A_WORD.has(name)));
  expect([...kept].sort()).toEqual([...expected].sort());
});
