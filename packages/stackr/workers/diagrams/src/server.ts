// The diagrams worker (stackr ADR-0049): Excalidraw's conversion and export over HTTP, as
// artifactr's `WorkerConverter` calls them (artifactr ADR-0090), in one warm headless Chromium,
// one job at a time.
//
// POST /mermaid   {source, deadline}                  -> {elements, files}
// POST /skeletons {skeletons, deadline}               -> {elements, files}
// POST /render    {diagram, files, as, deadline}      -> the SVG's or the PNG's bytes
// GET  /healthz                                       -> {"excalidraw": version}
//
// Each POST carries the worker's token. A call that fails answers a 4xx or a 5xx with
// {reason, message}: invalid, unsupported, too_large, timeout or crashed.

import { timingSafeEqual } from "node:crypto";
import { readFile } from "node:fs/promises";
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { extname, join, normalize } from "node:path";
import { type Browser, chromium, type Page, type Route } from "playwright-core";
import type { Converted, Diagram, Skeleton } from "./page";
import { EXCALIDRAW } from "./version";

/** The most seconds a call may take, whatever it asks for. */
const DEADLINE = 10;
/** The most bytes a call may send: a render's diagram and its images, as base64. */
const MAX_BODY = 24 * 1024 * 1024;
/** The most elements a diagram may hold, tombstones included (artifactr ADR-0086). */
const MAX_ELEMENTS = 2_000;
/** The longest Mermaid source, in characters. */
const MAX_MERMAID = 50_000;
/** The most skeletons a call may send. */
const MAX_SKELETONS = 500;

/** The page's origin, which no network has: every request to it is answered from `PAGE_DIR`. */
const ORIGIN = "http://diagrams.invalid";
/** Where the page and Excalidraw's faces are. */
const PAGE_DIR = process.env.PAGE_DIR ?? join(import.meta.dirname, "page");

/**
 * The page's policy: its own scripts, and `'unsafe-eval'`, which Excalidraw's font subsetting
 * needs, here alone in lattice (artifactr ADR-0088). It connects to nothing.
 */
const POLICY = [
  "default-src 'none'",
  "script-src 'self' 'unsafe-eval'",
  "worker-src 'self' blob:",
  "style-src 'self' 'unsafe-inline'",
  "font-src 'self' data:",
  "img-src 'self' data: blob:",
  "connect-src 'self' data: blob:",
  "base-uri 'none'",
  "form-action 'none'",
].join("; ");

const TYPES: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".woff2": "font/woff2",
  ".ttf": "font/ttf",
  ".json": "application/json",
};

type Reason = "invalid" | "unsupported" | "too_large" | "timeout" | "crashed";

const STATUS: Record<Reason, number> = {
  invalid: 422,
  unsupported: 422,
  too_large: 413,
  timeout: 504,
  crashed: 500,
};

/** A call that can't be carried out, and why. */
class Refused extends Error {
  readonly reason: Reason;

  constructor(reason: Reason, message: string) {
    super(message);
    this.reason = reason;
  }
}

const token = process.env.WORKER_TOKEN ?? "";
if (token.length < 32) {
  throw new Error("WORKER_TOKEN must be set, at least 32 characters");
}

/** The warm browser and its page, made again after a job that failed or ran out of time. */
class Chromium {
  private browser: Browser | undefined;
  private page: Page | undefined;
  /** Requests the page made to anywhere but its own origin, each refused. */
  refused = 0;

  async ready(): Promise<Page> {
    if (this.page !== undefined && !this.page.isClosed()) return this.page;
    if (this.browser === undefined || !this.browser.isConnected()) {
      this.browser = await chromium.launch({
        args: ["--js-flags=--max-old-space-size=512", "--disable-dev-shm-usage"],
      });
    }
    const context = await this.browser.newContext({ serviceWorkers: "block" });
    await context.route("**/*", (route) => this.serve(route));
    const page = await context.newPage();
    await page.goto(`${ORIGIN}/index.html`);
    await page.waitForFunction(() => window.diagrams !== undefined);
    this.page = page;
    return page;
  }

  /** Throw the page away, and the browser if it is gone, so the next job starts clean. */
  async recycle(): Promise<void> {
    const page = this.page;
    this.page = undefined;
    await page
      ?.context()
      .close()
      .catch(() => undefined);
    if (this.browser !== undefined && !this.browser.isConnected()) this.browser = undefined;
  }

  private async serve(route: Route): Promise<void> {
    const url = new URL(route.request().url());
    if (url.origin !== ORIGIN) {
      this.refused += 1;
      console.warn(`refused a request out: ${url.origin}`);
      await route.abort("blockedbyclient");
      return;
    }
    const path = normalize(decodeURIComponent(url.pathname)).replace(/^(\.\.[/\\])+/, "");
    try {
      const body = await readFile(join(PAGE_DIR, path));
      const headers: Record<string, string> = {
        "content-type": TYPES[extname(path)] ?? "application/octet-stream",
      };
      if (path.endsWith(".html")) headers["content-security-policy"] = POLICY;
      await route.fulfill({ status: 200, headers, body });
    } catch {
      await route.fulfill({ status: 404, body: "" });
    }
  }
}

const chromiumWarm = new Chromium();
let queue: Promise<unknown> = Promise.resolve();

/** Run a job alone, within what is left of its deadline once it starts; else `timeout`. */
function alone<T>(deadline: number, job: (page: Page) => Promise<T>): Promise<T> {
  const arrived = Date.now();
  const run = async (): Promise<T> => {
    const left = deadline * 1000 - (Date.now() - arrived);
    if (left <= 0) throw new Refused("timeout", `waited past its deadline of ${deadline}s`);
    let timer: NodeJS.Timeout | undefined;
    const late = new Promise<never>((_, reject) => {
      timer = setTimeout(() => reject(new Refused("timeout", `took more than ${deadline}s`)), left);
    });
    try {
      const page = await Promise.race([chromiumWarm.ready(), late]);
      return await Promise.race([job(page), late]);
    } catch (error) {
      await chromiumWarm.recycle();
      throw error;
    } finally {
      clearTimeout(timer);
    }
  };
  const result = queue.then(run, run);
  queue = result.catch(() => undefined);
  return result;
}

function deadlineOf(body: Record<string, unknown>): number {
  const asked = body.deadline;
  if (asked === undefined) return DEADLINE;
  if (typeof asked !== "number" || !Number.isFinite(asked)) {
    throw new Refused("invalid", "deadline is a number of seconds");
  }
  return Math.min(asked, DEADLINE);
}

function within(what: string, size: number, most: number): void {
  if (size > most) throw new Refused("too_large", `${what} is ${size}: at most ${most}`);
}

/** A conversion's elements, held to a diagram's limit. */
function held(converted: Converted): Converted {
  within("what it makes", converted.elements.length, MAX_ELEMENTS);
  return converted;
}

/** What the page threw, as the agent's fault when Mermaid couldn't read its source. */
function failed(error: unknown, invalid: boolean): Refused {
  if (error instanceof Refused) return error;
  const said = error instanceof Error ? error.message : String(error);
  // Mermaid's own words, with where it stopped, and not the page's stack.
  const words = said.replace(/^page\.evaluate: (Error: )?/, "").split(/\n\s+at /)[0] ?? said;
  if (invalid) return new Refused("invalid", words);
  console.error(said);
  return new Refused("crashed", "the worker failed");
}

async function mermaid(body: Record<string, unknown>): Promise<Converted> {
  const source = body.source;
  if (typeof source !== "string") throw new Refused("invalid", "source is Mermaid's text");
  within("Mermaid's source", source.length, MAX_MERMAID);
  return held(
    await alone(deadlineOf(body), async (page) => {
      try {
        return await page.evaluate((text) => window.diagrams.mermaid(text), source);
      } catch (error) {
        throw failed(error, true);
      }
    }),
  );
}

async function skeletons(body: Record<string, unknown>): Promise<Converted> {
  const given = body.skeletons;
  if (!Array.isArray(given)) throw new Refused("invalid", "skeletons is a list");
  within("the skeletons", given.length, MAX_SKELETONS);
  return held(
    await alone(deadlineOf(body), async (page) => {
      try {
        return await page.evaluate((each) => window.diagrams.skeletons(each), given as Skeleton[]);
      } catch (error) {
        throw failed(error, true);
      }
    }),
  );
}

async function render(body: Record<string, unknown>): Promise<[string, Buffer]> {
  const diagram = body.diagram as Diagram | undefined;
  const files = (body.files ?? {}) as Record<string, string>;
  const as = body.as;
  if (typeof diagram !== "object" || diagram === null || typeof diagram.elements !== "object") {
    throw new Refused("invalid", "diagram is a diagram's JSON");
  }
  if (as !== "svg" && as !== "png") throw new Refused("invalid", "as is svg or png");
  within("the diagram's elements", Object.keys(diagram.elements).length, MAX_ELEMENTS);
  const made = await alone(deadlineOf(body), async (page) => {
    try {
      return await page.evaluate(([d, f, a]) => window.diagrams.render(d, f, a), [
        diagram,
        files,
        as,
      ] as const);
    } catch (error) {
      throw failed(error, false);
    }
  });
  return as === "svg"
    ? ["image/svg+xml", Buffer.from(made, "utf8")]
    : ["image/png", Buffer.from(made, "base64")];
}

async function read(request: IncomingMessage): Promise<Record<string, unknown>> {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of request) {
    size += (chunk as Buffer).length;
    within("the call", size, MAX_BODY);
    chunks.push(chunk as Buffer);
  }
  try {
    const body: unknown = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    if (typeof body !== "object" || body === null || Array.isArray(body)) throw new Error();
    return body as Record<string, unknown>;
  } catch {
    throw new Refused("invalid", "the call is a JSON object");
  }
}

function allowed(request: IncomingMessage): boolean {
  const given = Buffer.from(request.headers.authorization ?? "");
  const expected = Buffer.from(`Bearer ${token}`);
  return given.length === expected.length && timingSafeEqual(given, expected);
}

function reply(response: ServerResponse, status: number, type: string, body: Buffer): void {
  response.writeHead(status, { "content-type": type, "content-length": body.length });
  response.end(body);
}

function json(response: ServerResponse, status: number, body: unknown): void {
  reply(response, status, "application/json", Buffer.from(JSON.stringify(body)));
}

const CALLS: Record<string, (body: Record<string, unknown>) => Promise<unknown>> = {
  "/mermaid": mermaid,
  "/skeletons": skeletons,
};

const server = createServer(async (request, response) => {
  try {
    if (request.method === "GET" && request.url === "/healthz") {
      json(response, 200, { excalidraw: EXCALIDRAW });
      return;
    }
    const path = request.url ?? "";
    if (request.method !== "POST" || !(path in CALLS || path === "/render")) {
      json(response, 404, { reason: "invalid", message: "no such call" });
      return;
    }
    if (!allowed(request)) {
      json(response, 401, { reason: "invalid", message: "the worker's token is needed" });
      return;
    }
    const body = await read(request);
    if (path === "/render") {
      const [type, bytes] = await render(body);
      reply(response, 200, type, bytes);
      return;
    }
    json(
      response,
      200,
      await (CALLS[path] as (b: Record<string, unknown>) => Promise<unknown>)(body),
    );
  } catch (error) {
    const refused = failed(error, false);
    json(response, STATUS[refused.reason], { reason: refused.reason, message: refused.message });
  }
});

await chromiumWarm.ready();
server.listen(Number(process.env.PORT ?? 8080), "0.0.0.0", () => {
  console.log(`diagrams worker: Excalidraw ${EXCALIDRAW}, ready`);
});

for (const signal of ["SIGTERM", "SIGINT"] as const) {
  process.on(signal, () => {
    server.close();
    void chromiumWarm.recycle().finally(() => process.exit(0));
  });
}
