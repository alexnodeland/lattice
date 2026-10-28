import { pageTitle } from "@portalr/ui";
/**
 * The app as a route, over a stubbed server and a stubbed artifactr stream, for route-level tests:
 * alice is signed in, a member of acme who can open notes; a test's own `serve` answers the rest,
 * and its `answer` what the stream says of each command. reflexr's stream replays the log a test
 * gives it, and artifactr's an empty one. The query client is the app's own, with its retries.
 */

import {
  type Config,
  createApi,
  createCommands,
  createQueries,
  createQueryClient,
  Signed,
} from "@portalr/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, createRouter, RouterProvider } from "@tanstack/react-router";
import { vi } from "vitest";
import { render } from "vitest-browser-react";
import { routeTree } from "../routeTree.gen";

const CONFIG: Config = {
  supabase: { url: "http://127.0.0.1:9", key: "sb_publishable_x" },
  surfaces: { artifactr: "/artifactr/v1", reflexr: "/reflexr/v1", grantr: "", portalr: "" },
  readers: { tempo: false },
  people: false,
  editors: { "files:wordcraft": "https://wordcraft.example.test/" },
  apps: null,
  links: {},
  aliases: {},
  replay: false,
};

/** alice, signed in, as Supabase Auth would say, without asking it. */
class Alice extends Signed {
  override signedIn = async () => "alice";
}

/** Nobody signed in: the sign-in page's world. */
class Nobody extends Signed {
  override signedIn = async () => null;
}

/** A test's answers, past who alice is: undefined for none. */
export type Serve = (request: Request, path: string) => Promise<Response | undefined>;

/**
 * What the stream says of a command: its rejection's type, or its type, message and fields, or
 * null to carry it out; "close" closes the connection for good instead of answering.
 */
export type Answer = (command: {
  type: string;
}) =>
  | string
  | ({ readonly type: string; readonly message: string } & Readonly<Record<string, unknown>>)
  | null;

/** A WebSocket that replays its library's log, or none, then answers each command as `answer` says. */
function socketAnswering(
  answer: Answer,
  logs: { readonly artifactr: readonly unknown[]; readonly reflexr: readonly unknown[] },
  /** A stream whose replay never completes, as one still catching up on its history. */
  replaying?: "artifactr" | "reflexr",
) {
  return class {
    onopen: (() => void) | null = null;
    onmessage: ((message: { data: string }) => void) | null = null;
    onclose: ((closed: { code: number }) => void) | null = null;
    readonly #log: readonly unknown[];
    readonly #replaying: boolean;

    constructor(url: string) {
      const library = url.includes("/reflexr/") ? "reflexr" : "artifactr";
      this.#log = logs[library];
      this.#replaying = replaying === library;
      queueMicrotask(() => this.onopen?.());
    }

    #emit(frame: unknown) {
      queueMicrotask(() => this.onmessage?.({ data: JSON.stringify(frame) }));
    }

    send(data: string) {
      const frame = JSON.parse(data) as { type: string; command_id?: string; command?: never };
      if (frame.type === "hello") {
        this.#emit({ type: "welcome", head_seq: this.#log.length });
        for (const event of this.#log) {
          this.#emit(event);
        }
        if (!this.#replaying) {
          this.#emit({ type: "replay_complete" });
        }
        return;
      }
      const refused = answer(frame.command ?? { type: "" });
      if (refused === "close") {
        // The connection ends for good, as the server refusing the session would end it.
        this.onclose?.({ code: 4403 });
        return;
      }
      const rejection = typeof refused === "string" ? { type: refused, message: refused } : refused;
      this.#emit({
        type: "command_result",
        command_id: frame.command_id,
        ok: rejection === null,
        ...(rejection !== null && { rejection }),
      });
    }

    close() {}
  };
}

/** The server: who alice is, in every tenant and in acme, then `serve`'s answers, then a refusal. */
function server(serve: Serve) {
  return async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = new Request(input, init);
    const path = new URL(request.url).pathname;
    if (path === "/grantr/v1/me") {
      const tenant = request.headers.get("X-Tenant");
      if (tenant !== null && tenant !== "acme") {
        // Alice is a member of acme alone.
        return Response.json({ detail: "the caller isn't a member" }, { status: 403 });
      }
      return tenant !== null
        ? Response.json({ tenant: "acme", user: "alice", roles: [], workspaces: ["notes"] })
        : Response.json({ memberships: [{ tenant: "acme", user: "alice", roles: ["member"] }] });
    }
    return (await serve(request, path)) ?? Response.json({ detail: "not here" }, { status: 403 });
  };
}

/**
 * What a test changes of the app's world: artifactr's and reflexr's logs, the config's surfaces,
 * the editors the deployment hosts, WordCraft's unless told, and the origin its mini apps run on,
 * none unless told.
 */
export interface World {
  readonly artifactrLog?: readonly unknown[];
  readonly reflexrLog?: readonly unknown[];
  /** A stream that is still catching up on its history: its replay never completes. */
  readonly replaying?: "artifactr" | "reflexr";
  readonly surfaces?: Partial<Config["surfaces"]>;
  readonly editors?: Config["editors"];
  readonly apps?: Config["apps"];
  /** The portal's own origin, and its other origins' places, which it doesn't name unless told. */
  readonly origin?: Config["origin"];
  readonly aliases?: Config["aliases"];
  /** Each connected app's address, by its integration. */
  readonly links?: Config["links"];
  /** The tools the deployment reads, past the defaults. */
  readonly readers?: Config["readers"];
  /** Whether the deployment records session replays, which it doesn't unless told. */
  readonly replay?: boolean;
  /** Whether nobody is signed in, which alice is unless told. */
  readonly signedOut?: boolean;
}

/** The app, opened at `path`, over `serve` and streams that answer as `answer` does. */
export async function open(
  path: string,
  serve: Serve,
  answer: Answer = () => null,
  world: World = {},
) {
  const fetched = vi.fn(server(serve));
  vi.stubGlobal("fetch", fetched);
  vi.stubGlobal(
    "WebSocket",
    socketAnswering(
      answer,
      { artifactr: world.artifactrLog ?? [], reflexr: world.reflexrLog ?? [] },
      world.replaying,
    ),
  );
  const queryClient = createQueryClient(() => undefined);
  const config = {
    ...CONFIG,
    surfaces: { ...CONFIG.surfaces, ...world.surfaces },
    editors: world.editors ?? CONFIG.editors,
    apps: world.apps ?? CONFIG.apps,
    ...(world.origin !== undefined && { origin: world.origin }),
    aliases: world.aliases ?? CONFIG.aliases,
    links: world.links ?? CONFIG.links,
    readers: { ...CONFIG.readers, ...world.readers },
    replay: world.replay ?? CONFIG.replay,
  };
  const api = createApi(config.surfaces, () => ({ token: "t0k3n" }));
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [path] }),
    context: {
      config,
      signed: world.signedOut
        ? new Nobody(config, () => undefined)
        : new Alice(config, () => undefined),
      api,
      queries: createQueries(api),
      commands: createCommands(api, () => undefined),
      queryClient,
      title: (...parts: string[]) => pageTitle(config.brand, "app", ...parts),
    },
  });
  const screen = await render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { screen, router, fetched, queryClient };
}
