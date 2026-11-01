/**
 * The REST clients, one per surface, typed from each package's committed OpenAPI document by
 * openapi-fetch, and each request carrying the session.
 */

import createClient, {
  type Client,
  type FetchResponse,
  type MaybeOptionalInit,
  type Middleware,
} from "openapi-fetch";
import type { paths as ArtifactrPaths } from "./generated/artifactr.openapi";
import type { Calls } from "./generated/calls";
import type { paths as FilesPaths } from "./generated/files.openapi";
import type { paths as GrantrPaths } from "./generated/grantr.openapi";
import type { components as Portalr, paths as PortalrPaths } from "./generated/portalr.openapi";
import type { paths as ReflexrPaths } from "./generated/reflexr.openapi";
import type { paths as RelayrPaths } from "./generated/relayr.openapi";
import { type Session, sessionHeaders } from "./session";

/** Where each surface is mounted, as the application's `config.json` says. */
export interface Surfaces {
  /** artifactr's router, such as `/artifactr/v1`. */
  readonly artifactr: string;
  /** reflexr's router, such as `/reflexr/v1`. */
  readonly reflexr: string;
  /**
   * The origin grantr's router is mounted at; its paths carry `/grantr/v1` themselves, as
   * portalr's carry `/portalr/v1`, so portalr's client is on it too.
   */
  readonly grantr: string;
  /**
   * The origin relayr's tracker reads are mounted at, whose paths carry `/relayr/v1`; none where
   * the application has no tracker.
   */
  readonly relayr?: string | null | undefined;
}

/** The methods the clients call an operation by. */
type Method = "get" | "put" | "post" | "delete" | "patch";

/** A document's paths that have an operation for the method. */
type PathsWith<Paths, M extends Method> = {
  [P in keyof Paths]: Paths[P] extends { [K in M]: unknown } ? P : never;
}[keyof Paths];

/** The keys of `T` that aren't optional. */
type RequiredKeys<T> = {
  [K in keyof T]-?: Record<never, never> extends Pick<T, K> ? never : K;
}[keyof T];

/** openapi-fetch's last argument: required where the operation's parameters or body are. */
type InitParam<Init> =
  RequiredKeys<Init> extends never
    ? [(Init & { [key: string]: unknown })?]
    : [Init & { [key: string]: unknown }];

/**
 * What an operation calls, as `Calls` says: its command, the commands its caller picks one of,
 * `null` for one that calls none, or `"frames"` where its body's command frames name theirs.
 */
export type CommandOf<C, Path, M extends Method> = Path extends keyof C
  ? M extends keyof C[Path]
    ? C[Path][M]
    : never
  : never;

/** One of a named client's methods: openapi-fetch's, with the operation's command first. */
type NamedMethod<Paths, C, M extends Method> = <
  Path extends PathsWith<Paths, M>,
  Init extends MaybeOptionalInit<Paths[Path], M & keyof Paths[Path]>,
>(
  command: CommandOf<C, Path, M>,
  url: Path,
  ...init: InitParam<Init>
) => Promise<
  Paths[Path][M & keyof Paths[Path]] extends infer O extends Record<string | number, unknown>
    ? FetchResponse<O, Init, `${string}/${string}`>
    : never
>;

/**
 * A surface's client, each of whose requests names the command it calls, as its document's
 * `x-lattice-command` says, so a request that calls none or another fails `tsc` (lattice
 * RFC-0014, portalr ADR-0096). The name isn't sent: the server knows what each operation calls.
 */
export interface Named<Paths, C> {
  readonly GET: NamedMethod<Paths, C, "get">;
  readonly PUT: NamedMethod<Paths, C, "put">;
  readonly POST: NamedMethod<Paths, C, "post">;
  readonly DELETE: NamedMethod<Paths, C, "delete">;
  readonly PATCH: NamedMethod<Paths, C, "patch">;
}

/** The client, as one whose every request names its command first. */
export function withCommands<Paths extends object, C>(client: Client<Paths>): Named<Paths, C> {
  const drop =
    (method: (url: never, ...init: never[]) => unknown) =>
    (_command: unknown, url: never, ...init: never[]) =>
      method(url, ...init);
  return {
    GET: drop(client.GET),
    PUT: drop(client.PUT),
    POST: drop(client.POST),
    DELETE: drop(client.DELETE),
    PATCH: drop(client.PATCH),
  } as unknown as Named<Paths, C>;
}

export interface Api {
  readonly artifactr: Named<ArtifactrPaths, Calls["artifactr"]>;
  /** Native files' routes, which an application mounts beside artifactr's, on its surface. */
  readonly files: Named<FilesPaths, Calls["files"]>;
  readonly reflexr: Named<ReflexrPaths, Calls["reflexr"]>;
  readonly grantr: Named<GrantrPaths, Calls["grantr"]>;
  readonly portalr: Named<PortalrPaths, Calls["portalr"]>;
  /** relayr's tracker reads, or none where the application has no tracker. */
  readonly relayr: Named<RelayrPaths, Calls["relayr"]> | null;
}

/** The clients, each sending the session that `session()` returns at the time. */
export function createApi(surfaces: Surfaces, session: () => Session): Api {
  const signed: Middleware = {
    onRequest({ request }) {
      for (const [name, value] of Object.entries(sessionHeaders(session()))) {
        request.headers.set(name, value);
      }
      return request;
    },
  };
  const artifactr = createClient<ArtifactrPaths>({ baseUrl: surfaces.artifactr });
  const files = createClient<FilesPaths>({ baseUrl: surfaces.artifactr });
  const reflexr = createClient<ReflexrPaths>({ baseUrl: surfaces.reflexr });
  const grantr = createClient<GrantrPaths>({ baseUrl: surfaces.grantr });
  const portalr = createClient<PortalrPaths>({ baseUrl: surfaces.grantr });
  const relayr =
    surfaces.relayr == null ? null : createClient<RelayrPaths>({ baseUrl: surfaces.relayr });
  for (const client of [artifactr, files, reflexr, grantr, portalr, relayr] as const) {
    client?.use(signed);
  }
  return {
    artifactr: withCommands(artifactr),
    files: withCommands(files),
    reflexr: withCommands(reflexr),
    grantr: withCommands(grantr),
    portalr: withCommands(portalr),
    relayr: relayr === null ? null : withCommands(relayr),
  };
}

/** The headers that name a request's tenant. */
export const named = (tenant: string) => ({ headers: { "X-Tenant": tenant } });

/** What the UIs need of the deployment: its Supabase project, the surfaces and the tools. */
export type Config = Portalr["schemas"]["Config"];

/** Read `config.json`, which portalr's router serves at `/portalr/config.json` on `origin`. */
export async function readConfig(origin: string): Promise<Config> {
  const client = withCommands<PortalrPaths, Calls["portalr"]>(createClient({ baseUrl: origin }));
  const { data, response } = await client.GET(null, "/portalr/config.json");
  if (data === undefined) {
    throw new Error(`config.json answered ${response.status}`);
  }
  return data;
}
