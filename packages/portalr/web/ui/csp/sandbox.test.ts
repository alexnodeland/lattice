/**
 * Mini apps' sandbox in Chromium (lattice RFC-0005, portalr ADR-0051): the sandbox page as app's
 * build writes it, served on an origin of its own under the app's policy, framed by the harness's
 * page through ui's own `AppFrame` and bridge. An app tries every way out it has to a sink on
 * 127.0.0.1, over HTTP and over UDP, and the sink hears nothing; but for WebRTC from a frame the
 * app makes, which no policy refuses in Chromium, and which the sink hears.
 */

import { createSocket } from "node:dgram";
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import { type Browser, chromium, type Page } from "playwright";
import { afterAll, beforeAll, expect, inject, test, vi } from "vitest";

let browser: Browser;

/** Every request the HTTP sink heard, and every connection made to it, even one never used. */
const heard: string[] = [];
const http = createServer((request, response) => {
  heard.push(`${request.method} ${request.url}`);
  response.end();
});
http.on("connection", () => heard.push("a connection"));
http.on("upgrade", (request, socket) => {
  heard.push(`upgrade ${request.url}`);
  socket.destroy();
});
const udp = createSocket("udp4");
udp.on("message", () => heard.push("a UDP datagram"));

let sink: string;
let stun: string;

beforeAll(async () => {
  browser = await chromium.launch();
  await new Promise<void>((listening) => http.listen(0, "127.0.0.1", listening));
  await new Promise<void>((bound) => udp.bind(0, "127.0.0.1", bound));
  sink = `http://127.0.0.1:${(http.address() as AddressInfo).port}`;
  stun = `stun:127.0.0.1:${udp.address().port}`;
});

afterAll(async () => {
  udp.close();
  http.close();
  await browser.close();
});

/** The harness's page, running `html` as a mini app in the sandbox. */
async function running(html: string): Promise<Page> {
  heard.length = 0;
  const page = await browser.newPage();
  const search = new URLSearchParams({ app: html, apps: inject("apps") });
  await page.goto(`${inject("harness")}?${search}`);
  return page;
}

/** Long enough for the sandbox, the app and the bridge to start on a busy CI runner. */
const SETTLED = { timeout: 15_000 };

/** The app's own frame, inside the sandbox's. */
const appFrame = (page: Page) =>
  page.frames().find((frame) => frame.parentFrame()?.parentFrame() === page.mainFrame());

/** The app's frame's height, which the app asks for through the bridge. */
const height = (page: Page) =>
  page.getByTitle("Probe: an app made by the agent").evaluate((frame) => frame.style.height);

/** An app whose script runs `body` in its document's body, then asks for its height as `said`. */
const script = (body: string, said: string) =>
  `<body><script>${body};parent.postMessage({jsonrpc:"2.0",method:"ui/notifications/size-changed",params:{height:${said}}},"*")</script>`;

test("the sandbox's script and the app's run under the policy, and the app reaches the bridge", async () => {
  // A request answered by the host's context, then the frame's height said from the answer.
  const page = await running(
    `<script>addEventListener("message",(e)=>{const m=JSON.parse(JSON.stringify(e.data));if(m.id===1)parent.postMessage({jsonrpc:"2.0",method:"ui/notifications/size-changed",params:{height:m.result.hostInfo.name==="portalr"?432:0}},"*")});parent.postMessage({jsonrpc:"2.0",id:1,method:"ui/initialize",params:{}},"*")</script>`,
  );
  await expect.poll(() => height(page), SETTLED).toBe("432px");
  await page.close();
});

/** Each way out an app has, by name, as a script that tries it. */
const WAYS_OUT = (to: string, peer: string): Record<string, string> => ({
  fetch: `fetch("${to}/fetch").catch(()=>{})`,
  XHR: `const x=new XMLHttpRequest();x.open("GET","${to}/xhr");x.send()`,
  WebSocket: `new WebSocket("${to.replace("http", "ws")}/ws")`,
  EventSource: `new EventSource("${to}/events")`,
  "a beacon": `navigator.sendBeacon("${to}/beacon","x")`,
  "an image": `new Image().src="${to}/image"`,
  "a CSS beacon and font": `document.head.insertAdjacentHTML("beforeend","<style>body{background:url(${to}/css)}@font-face{font-family:f;src:url(${to}/font)}body{font-family:f}</style>");document.body.append("text")`,
  "prefetch, preconnect, DNS prefetch and preload": `for(const rel of ["prefetch","preconnect","dns-prefetch","preload"]){const l=document.createElement("link");l.rel=rel;l.as="image";l.href="${to}/"+rel;document.head.append(l)}`,
  "a worker": `new Worker("${to}/worker")`,
  "a popup": `open("${to}/popup")`,
  "a form": `const f=document.createElement("form");f.method="post";f.action="${to}/form";document.body.append(f);f.submit()`,
  "the top's navigation": `top.location="${to}/top"`,
  "a frame of the sink's": `const f=document.createElement("iframe");f.src="${to}/frame";document.body.append(f)`,
  "a data: frame": `const f=document.createElement("iframe");f.src="data:text/html,<img src=${to}/data>";document.body.append(f)`,
  "a javascript: frame": `const f=document.createElement("iframe");f.src="javascript:'<img src=${to}/javascript>'";document.body.append(f)`,
  "a srcdoc frame's fetch": `const f=document.createElement("iframe");f.srcdoc="<script>fetch('${to}/srcdoc')<\\/script>";document.body.append(f)`,
  "WebRTC in the app's window": `const p=new RTCPeerConnection({iceServers:[{urls:"${peer}"}]});p.createDataChannel("x");p.createOffer().then((o)=>p.setLocalDescription(o))`,
});

/** Each way out that navigates the app's frame, tried once the app has said it ran the rest. */
const LEAVING = (to: string): Record<string, string> => ({
  "a link's ping": `const a=document.createElement("a");a.href="${to}/link";a.ping="${to}/ping";document.body.append(a);a.click()`,
  "a refresh": `document.head.insertAdjacentHTML("beforeend",'<meta http-equiv="refresh" content="0;url=${to}/refresh">')`,
  "the frame's own navigation": `location.href="${to}/navigation"`,
});

/** `ways`, each tried in turn, whatever the one before it threw. */
const tried = (ways: Record<string, string>) =>
  Object.values(ways)
    .map((way) => `try{${way}}catch{}`)
    .join(";");

test("every way out an app has is refused, and the sink hears nothing", async () => {
  const ways = WAYS_OUT(sink, stun);
  const said = 300 + Object.keys(ways).length;
  const page = await running(
    script(`${tried(ways)};setTimeout(()=>{${tried(LEAVING(sink))}},100)`, `${said}`),
  );
  await expect.poll(() => height(page), SETTLED).toBe(`${said}px`);
  // Long enough for a request, a connection or ICE's first datagram to have arrived.
  await page.waitForTimeout(3000);
  expect(heard).toEqual([]);
  await page.close();
});

test("WebRTC from a srcdoc frame the app makes still reaches the sink: not refused in Chromium", async () => {
  // The prelude takes WebRTC from the app's window alone; a frame's script runs in a window of its
  // own, which has it (portalr ADR-0051). If this ever fails, Chromium refuses it, and the ADR and
  // the label can say so.
  const peer = `const p=new RTCPeerConnection({iceServers:[{urls:'${stun}'}]});p.createDataChannel('x');p.createOffer().then((o)=>p.setLocalDescription(o))`;
  const page = await running(
    script(
      `const f=document.createElement("iframe");f.srcdoc="<script>${peer}<\\/script>";document.body.append(f)`,
      "321",
    ),
  );
  await expect.poll(() => height(page), SETTLED).toBe("321px");
  await vi.waitFor(() => expect(heard).toContain("a UDP datagram"), { timeout: 10_000 });
  await page.close();
});

test("a game's turns each write its state and read it back, so every turn's button comes back", async () => {
  // As create_app's description teaches: initialize, then each click writes the state, reads it
  // back from structuredContent, and draws everything from it in one render.
  const page = await running(
    `<body><button id="play" disabled>Play</button><output id="moves">0</output><script>
let state = { moves: 0 }, waiting = true, id = 0;
const pending = new Map();
const call = (method, params) => new Promise((done) => {
  pending.set(++id, done);
  parent.postMessage({ jsonrpc: "2.0", id, method, params }, "*");
});
const render = () => {
  document.getElementById("moves").textContent = String(state.moves);
  document.getElementById("play").disabled = waiting;
};
addEventListener("message", (e) => pending.get(e.data?.id)?.(e.data.result));
const read = async () => {
  const result = await call("tools/call", { name: "get_state", arguments: {} });
  state = { moves: result.structuredContent?.state?.moves ?? 0 };
};
document.getElementById("play").addEventListener("click", async () => {
  waiting = true; render();
  await call("tools/call", { name: "set_state", arguments: { patch: [{ op: "add", path: "/moves", value: state.moves + 1 }] } });
  await read();
  waiting = false; render();
});
call("ui/initialize", {}).then(read).then(() => { waiting = false; render(); });
</script>`,
  );
  await expect.poll(() => appFrame(page)?.isEnabled("#play"), SETTLED).toBe(true);
  for (const turn of ["1", "2", "3"]) {
    await appFrame(page)?.click("#play");
    await expect.poll(() => appFrame(page)?.textContent("#moves"), SETTLED).toBe(turn);
  }
  await page.close();
});

/** The app's frame's height as drawn, in pixels. */
const drawn = (page: Page) =>
  page
    .getByTitle("Probe: an app made by the agent")
    .evaluate((frame) => frame.getBoundingClientRect().height);

test("an app is shown whole without saying its size, and grows as it draws more", async () => {
  // Says a height of 0, as one measured before it was laid out, and then nothing.
  const page = await running(
    `<body style="margin:0"><div id="box" style="height:300px">Board</div><script>
parent.postMessage({ jsonrpc: "2.0", method: "ui/notifications/size-changed", params: { height: 0 } }, "*");
setTimeout(() => { document.getElementById("box").style.height = "420px"; }, 1500);
</script>`,
  );
  await expect.poll(() => drawn(page), SETTLED).toBe(300);
  await expect.poll(() => drawn(page), SETTLED).toBe(420);
  await page.close();
});

/** The frame's height once it has stopped changing: the same in two reads a second apart. */
async function settled(page: Page): Promise<number> {
  let last = -1;
  await expect
    .poll(
      async () => {
        const now = await drawn(page);
        const same = now === last;
        last = now;
        return same;
      },
      { ...SETTLED, interval: 1000 },
    )
    .toBe(true);
  return last;
}

for (const [fills, style] of [
  ["min-height", "min-height:100vh"],
  ["height", "height:100vh"],
] as const) {
  test(`an app that fills its window by ${fills}, with a margin round it, keeps its frame, not climbing`, async () => {
    // The body's default 8 px margin makes the document 16 px taller than the window it fills.
    const page = await running(`<body><div style="${style}">Board</div>`);
    const height = await settled(page);
    expect(height).toBeLessThanOrEqual(360 + 16);
    await page.close();
  });
}

test("an app at 100vh that draws more grows: the window's growth is ignored, its own isn't", async () => {
  const page = await running(
    `<body><div style="min-height:100vh">Board</div><div id="more"></div><script>
setTimeout(() => { document.getElementById("more").style.height = "300px"; }, 1500);
</script>`,
  );
  await expect.poll(() => drawn(page), SETTLED).toBeGreaterThanOrEqual(360 + 16 + 300);
  await page.close();
});

test("the app's frame fills the sandbox's window even where its body has no height to share", async () => {
  // iOS laid the app's frame out at 0 by 0 when it was sized by percentages of the sandbox's
  // body. Here the body is left at its own height, as auto: a frame at 100% of it is 150 tall.
  const page = await running(`<body style="margin:0">Board</body>`);
  await expect.poll(() => appFrame(page) !== undefined, SETTLED).toBe(true);
  const sandbox = appFrame(page)?.parentFrame();
  const sizes = () =>
    sandbox?.evaluate(() => {
      document.documentElement.style.height = "auto";
      document.body.style.height = "auto";
      const { width, height } = (
        document.querySelector("iframe") as Element
      ).getBoundingClientRect();
      return { frame: [width, height], window: [innerWidth, innerHeight] };
    });
  await expect.poll(async () => (await sizes())?.window[1], SETTLED).toBeGreaterThan(0);
  const { frame, window } = (await sizes()) ?? { frame: [], window: [] };
  expect(frame).toEqual(window);
  await page.close();
});

test("a tall app is shown whole up to twice the window, and scrolls inside its frame past it", async () => {
  const page = await running(`<body style="margin:0"><div style="height:3000px">Board</div>`);
  const twice = await page.evaluate(() => innerHeight * 2);
  await expect.poll(() => drawn(page), SETTLED).toBe(twice);
  await page.close();
});

test("an app plays through the sandbox's host: its answers, a refusal, and a render after each", async () => {
  // As create_app's description now teaches: `host.connect`, `host.call`, `host.onAnswer`.
  const page = await running(
    `<body><button id="play" disabled>Play</button><output id="moves">0</output><output id="said"></output><output id="theme"></output><script>
let state = { moves: 0 }, waiting = true, renders = 0;
const render = () => {
  renders += 1;
  document.getElementById("moves").textContent = String(state.moves);
  document.getElementById("play").disabled = waiting;
};
host.onAnswer(render);
document.getElementById("play").addEventListener("click", async () => {
  waiting = true; render();
  await host.call("set_state", { patch: [{ op: "add", path: "/moves", value: state.moves + 1 }] });
  state = (await host.call("get_state")).state;
  waiting = false; render();
});
host.connect().then(async () => {
  document.getElementById("theme").textContent = getComputedStyle(document.documentElement).colorScheme;
  await host.call("nope").catch((error) => { document.getElementById("said").textContent = "refused: " + error.message; });
  state = (await host.call("get_state")).state ?? { moves: 0 };
  state.moves = state.moves ?? 0;
  waiting = false; render();
});
</script>`,
  );
  const app = () => appFrame(page);
  await expect.poll(() => app()?.isEnabled("#play"), SETTLED).toBe(true);
  expect(await app()?.textContent("#said")).toMatch(/^refused: /);
  expect(await app()?.textContent("#theme")).toMatch(/^(light|dark)$/);
  for (const turn of ["1", "2", "3"]) {
    await app()?.click("#play");
    await expect.poll(() => app()?.textContent("#moves"), SETTLED).toBe(turn);
  }
  await page.close();
});

/** What the app wrote in `#said`, once it has. */
const said = (page: Page) => appFrame(page)?.textContent("#said");

test("a call the host never answers rejects, and the app's controls come back", async () => {
  // A message past 64 KB is dropped, unanswered, as one past the app's limit would be.
  const page = await running(
    `<body><button id="play" disabled>Play</button><output id="said"></output><script>
const play = document.getElementById("play");
host.connect().then(async () => {
  try {
    await host.call("set_state", { patch: [{ op: "add", path: "/big", value: "x".repeat(70000) }] });
  } catch (error) {
    document.getElementById("said").textContent = error.code + ": " + error.message;
  } finally {
    play.disabled = false;
  }
});
</script>`,
  );
  await expect.poll(() => said(page), { timeout: 30_000 }).toBe("timeout: the host did not answer");
  expect(await appFrame(page)?.isEnabled("#play")).toBe(true);
  await page.close();
});

test("a refusal rejects with isError, and an app's own requests are answered beside host's", async () => {
  const page = await running(
    `<body><output id="said"></output><script>
const lines = [];
addEventListener("message", (e) => {
  if (e.data && e.data.id === 7) lines.push("raw: " + JSON.stringify(e.data.result.structuredContent.state));
});
host.connect().then(async () => {
  await host.call("set_state", { patch: "not a patch" }).catch((error) => lines.push("refused: " + error.isError));
  parent.postMessage({ jsonrpc: "2.0", id: 7, method: "tools/call", params: { name: "get_state", arguments: {} } }, "*");
  const read = await host.call("get_state");
  lines.push("host: " + JSON.stringify(read.state));
  setTimeout(() => { document.getElementById("said").textContent = lines.join(" | "); }, 300);
});
</script>`,
  );
  await expect.poll(() => said(page), SETTLED).toBe("refused: true | raw: {} | host: {}");
  await page.close();
});

test("with host deleted, the frame and the bridge keep working by hand", async () => {
  const page = await running(
    `<body style="margin:0"><output id="said"></output><script>
delete window.host;
const lines = [];
addEventListener("message", (e) => {
  if (e.data && e.data.id === 1) lines.push("initialized");
  if (e.data && e.data.id === 2) lines.push("state " + JSON.stringify(e.data.result.structuredContent.state));
  document.getElementById("said").textContent = [typeof window.host, ...lines].join(" ");
});
const ask = (id, method, params) => parent.postMessage({ jsonrpc: "2.0", id, method, params }, "*");
ask(1, "ui/initialize", {});
ask(2, "tools/call", { name: "set_state", arguments: { patch: [{ op: "add", path: "/x", value: 1 }] } });
parent.postMessage({ jsonrpc: "2.0", method: "ui/notifications/size-changed", params: { height: 432 } }, "*");
</script>`,
  );
  await expect.poll(() => said(page), SETTLED).toBe('undefined initialized state {"x":1}');
  await expect.poll(() => drawn(page), SETTLED).toBe(432);
  await page.close();
});

test("a submission waits for the person however long, and gets their answer, once", async () => {
  const page = await running(
    `<body><output id="said"></output><script>
const lines = [];
const say = () => { document.getElementById("said").textContent = lines.join(" | "); };
host.connect().then(async () => {
  try { const sent = await host.call("submit", { values: { roll: 6 } }); lines.push("sent " + sent.submitted); }
  catch (error) { lines.push("failed " + (error.code || error.isError)); }
  say();
  try { await host.call("submit", { values: { roll: 1 } }); lines.push("sent again"); }
  catch (error) { lines.push("refused " + error.isError); }
  say();
});
</script>`,
  );
  const dialog = page.getByRole("alertdialog", { name: "Send this from Probe?" });
  await dialog.waitFor({ timeout: 15_000 });
  // Held past the 10 seconds a call that the host answers at once may take.
  await page.waitForTimeout(11_000);
  await dialog.getByRole("button", { name: "Send it", exact: true }).click();
  await expect.poll(() => said(page), SETTLED).toBe("sent true");
  await dialog.waitFor({ timeout: 15_000 });
  await dialog.getByRole("button", { name: "Don't send it" }).click();
  await expect.poll(() => said(page), SETTLED).toBe("sent true | refused true");
  await page.close();
});

test("host.onAnswer runs after the app's own code that awaited the answer", async () => {
  // An app that changes its state in an async function of its own, and leaves drawing to the hook.
  const page = await running(
    `<body><output id="moves">0</output><script>
let moves = 0;
host.onAnswer(() => { document.getElementById("moves").textContent = String(moves); });
async function move() {
  await host.call("set_state", { patch: [{ op: "add", path: "/moves", value: moves + 1 }] });
  await Promise.resolve();
  moves += 1;
}
host.connect().then(() => move()).then(() => move());
</script>`,
  );
  await expect.poll(() => appFrame(page)?.textContent("#moves"), SETTLED).toBe("2");
  await page.close();
});

test("the host's theme is kept on the app's document, and onContext hears it change", async () => {
  const page = await running(
    `<body><output id="said"></output><script>
let heard = 0;
const say = () => {
  const root = document.documentElement;
  document.getElementById("said").textContent = [
    root.dataset.theme,
    getComputedStyle(root).colorScheme,
    root.style.getPropertyValue("--color-background-primary") ? "coloured" : "plain",
    heard,
  ].join(" ");
};
host.onContext(() => { heard += 1; say(); });
host.connect().then(say);
</script>`,
  );
  await expect.poll(() => said(page), SETTLED).toMatch(/^light light coloured \d+$/);
  await page.evaluate(() => {
    document.documentElement.dataset.theme = "dark";
  });
  await expect.poll(() => said(page), SETTLED).toMatch(/^dark dark coloured [1-9]\d*$/);
  await page.close();
});

/** What the host's page says of the app in its console, `[app-frame]` first, as it is said. */
function warnings(page: Page): string[] {
  const said: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "warning" && message.text().startsWith("[app-frame]")) {
      said.push(message.text());
    }
  });
  return said;
}

/** The harness's page, with what it warns of the app kept from before the app runs. */
async function watched(html: string): Promise<{ page: Page; said: string[] }> {
  const page = await browser.newPage();
  const said = warnings(page);
  const search = new URLSearchParams({ app: html, apps: inject("apps") });
  await page.goto(`${inject("harness")}?${search}`);
  return { page, said };
}

test("an app that throws, or loads what its policy refuses, is said under it and in the console", async () => {
  const { page, said } = await watched(
    `<body><p>Board</p><img src="https://example.com/x.png"><script>Promise.reject(new Error("no level"));throw new Error("boom");</script>`,
  );
  await expect.poll(() => said.join("\n"), SETTLED).toContain("boom");
  await expect.poll(() => said.join("\n"), SETTLED).toContain("rejection: no level");
  await expect.poll(() => said.join("\n"), SETTLED).toContain("policy: img-src refused");
  expect(said.join("\n")).toContain("(https://example.com/x.png)");
  await page.getByText("The app reported a problem").click();
  await expect.poll(() => page.getByText(/error: .*boom/).count(), SETTLED).toBe(1);
  await page.close();
});

const NOTHING_YET = "The app hasn't drawn anything yet.";

/** Whether the page says its app hasn't drawn anything, now. */
const saysNothing = (page: Page) => page.getByText(NOTHING_YET, { exact: false }).count();

test("an app that never draws is said to after two looks, and its look said in the console", async () => {
  const { page, said } = await watched(
    `<body><div id="root"></div><canvas width="200" height="100"></canvas>`,
  );
  await expect.poll(() => said.some((line) => line.includes("drawn=not yet")), SETTLED).toBe(true);
  expect(await saysNothing(page)).toBe(0);
  await expect.poll(() => saysNothing(page), SETTLED).toBe(1);
  expect(said.join("\n")).toContain("drawn=nothing");
  await page.close();
});

test.each([
  [
    "a white background",
    `<body style="margin:0"><canvas width="200" height="100"></canvas><script>const c=document.querySelector("canvas").getContext("2d");c.fillStyle="#fff";c.fillRect(0,0,200,100)</script>`,
  ],
  [
    "a canvas drawn after 1.5 s",
    `<body style="margin:0"><canvas width="200" height="100"></canvas><script>setTimeout(()=>{const c=document.querySelector("canvas").getContext("2d");c.fillRect(0,0,200,100)},2500)</script>`,
  ],
  [
    "a DOM app with a hidden canvas",
    `<body><p>Score 0</p><canvas width="0" height="0" style="display:none"></canvas>`,
  ],
  [
    "a WebGL canvas",
    `<body style="margin:0"><canvas width="200" height="100"></canvas><script>const g=document.querySelector("canvas").getContext("webgl");if(g){g.clearColor(0,0,1,1);g.clear(g.COLOR_BUFFER_BIT)}else document.body.append("No WebGL here")</script>`,
  ],
])("an app with %s is never said to have drawn nothing", async (_, html) => {
  const { page, said } = await watched(html);
  await expect
    .poll(() => said.some((line) => line.includes("drawn=something")), SETTLED)
    .toBe(true);
  await page.waitForTimeout(5000);
  expect(await saysNothing(page)).toBe(0);
  expect(said.filter((line) => !line.startsWith("[app-frame] boot:"))).toEqual([]);
  expect(await page.getByText("The app reported a problem").count()).toBe(0);
  await page.close();
});

test("the wrapped getContext gives the browser's own context, on its canvas, and refuses as it does", async () => {
  const { page } = await watched(
    `<body><p>Probe</p><script>const c=document.createElement("canvas");const a=c.getContext("2d",{alpha:false});const b=document.createElement("canvas");const r=b.getContext("bitmaprenderer");document.body.dataset.ok=String(a===c.getContext("2d")&&a.canvas===c&&a.getContextAttributes().alpha===false&&c.getContext("webgl")===null&&(r===null||b.getContext("2d")===null))</script>`,
  );
  await expect
    .poll(() => appFrame(page)?.evaluate(() => document.body.dataset.ok), SETTLED)
    .toBe("true");
  await page.close();
});

test("a canvas the app asks for WebGL after its look is still given WebGL", async () => {
  const { page, said } = await watched(
    `<body><p>Tap to start</p><canvas width="200" height="100"></canvas><script>setTimeout(()=>{document.body.dataset.gl=String(!!document.querySelector("canvas").getContext("webgl"))},2500)</script>`,
  );
  await expect.poll(() => said.length, SETTLED).toBeGreaterThan(0);
  await expect
    .poll(() => appFrame(page)?.evaluate(() => document.body.dataset.gl), SETTLED)
    .toBe("true");
  await page.close();
});

test("an app that draws after it was said to have drawn nothing clears what was said", async () => {
  const { page } = await watched(
    `<body style="margin:0"><canvas width="200" height="100"></canvas><script>setTimeout(()=>{const c=document.querySelector("canvas").getContext("2d");c.fillRect(0,0,200,100)},7000)</script>`,
  );
  await expect.poll(() => saysNothing(page), SETTLED).toBe(1);
  await expect.poll(() => saysNothing(page), SETTLED).toBe(0);
  await page.close();
});

test("an app's document says the first five errors that differ, and no more", async () => {
  const { page, said } = await watched(
    `<body><p>Board</p><script>for(let i=0;i<20;i++)setTimeout(()=>{throw new Error("again")});for(let i=0;i<7;i++)setTimeout(()=>{throw new Error("boom "+i)});</script>`,
  );
  const errors = () => said.filter((line) => !line.startsWith("[app-frame] boot:"));
  await expect.poll(() => errors().length, SETTLED).toBe(5);
  await page.waitForTimeout(2000);
  expect(errors()).toHaveLength(5);
  expect(errors().filter((line) => line.includes("again"))).toHaveLength(1);
  await page.getByText("The app reported a problem").click();
  expect(
    await page
      .locator("details li")
      .filter({ hasNotText: /^boot:/ })
      .count(),
  ).toBe(5);
  await page.close();
});
