/**
 * The REST clients, one per surface, typed from each package's committed OpenAPI document by
 * openapi-fetch, and each request carrying the session.
 */

import createClient, { type Client, type Middleware } from "openapi-fetch";
import type { paths as ArtifactrPaths } from "./generated/artifactr.openapi";
import type { paths as GrantrPaths } from "./generated/grantr.openapi";
import type { components as Portalr, paths as PortalrPaths } from "./generated/portalr.openapi";
import type { paths as ReflexrPaths } from "./generated/reflexr.openapi";
import { type Session, sessionHeaders } from "./session";

/** Where each surface is mounted, as the application's `config.json` says. */
export interface Surfaces {
  /** artifactr's router, such as `/artifactr/v1`. */
  readonly artifactr: string;
  /** reflexr's router, such as `/reflexr/v1`. */
  readonly reflexr: string;
  /** The origin grantr's router is mounted at; its paths carry `/grantr/v1` themselves. */
  readonly grantr: string;
}

export interface Api {
  readonly artifactr: Client<ArtifactrPaths>;
  readonly reflexr: Client<ReflexrPaths>;
  readonly grantr: Client<GrantrPaths>;
}

/** The three clients, each sending the session that `session()` returns at the time. */
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
  const reflexr = createClient<ReflexrPaths>({ baseUrl: surfaces.reflexr });
  const grantr = createClient<GrantrPaths>({ baseUrl: surfaces.grantr });
  for (const client of [artifactr, reflexr, grantr] as const) {
    client.use(signed);
  }
  return { artifactr, reflexr, grantr };
}

/** What the UIs need of the deployment: its Supabase project, the surfaces and the tools. */
export type Config = Portalr["schemas"]["Config"];

/** Read `config.json`, which portalr's router serves at `/portalr/config.json` on `origin`. */
export async function readConfig(origin: string): Promise<Config> {
  const { data, response } = await createClient<PortalrPaths>({ baseUrl: origin }).GET(
    "/portalr/config.json",
  );
  if (data === undefined) {
    throw new Error(`config.json answered ${response.status}`);
  }
  return data;
}
