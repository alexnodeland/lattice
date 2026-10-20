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

test("an app that fills its window keeps a frame at least as tall as it started", async () => {
  const page = await running(`<body style="margin:0"><div style="height:100vh">Board</div>`);
  await page.waitForTimeout(1500);
  expect(await drawn(page)).toBeGreaterThanOrEqual(360);
  await page.close();
});

test("a tall app is shown whole up to twice the window, and scrolls inside its frame past it", async () => {
  const page = await running(`<body style="margin:0"><div style="height:3000px">Board</div>`);
  // The harness's window is 720 px tall: its cap is twice that.
  await expect.poll(() => drawn(page), SETTLED).toBe(1440);
  await page.close();
});
