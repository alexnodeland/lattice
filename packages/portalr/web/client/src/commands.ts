/**
 * Commands sent over a library's REST rather than its stream, for an answer to every one.
 *
 * A stream answers a command it can't read with an error frame that names no command, so a
 * command typed by hand, such as a rule's JSON, would never settle there. Its REST route answers
 * each request: carried out, refused with the library's rejection, or refused by FastAPI's
 * validation when the body isn't a command at all (portalr ADR-0020).
 */

import type { components as Grantr } from "./generated/grantr.openapi";
import type { components } from "./generated/reflexr.openapi";
import { type Api, named } from "./rest";

type Command = components["schemas"]["Command"];
type Result = components["schemas"]["CommandResult"];
type GrantRequest = Grantr["schemas"]["GrantRequest"];
type Restriction = Grantr["schemas"]["Restriction"];
type AuditEntry = Grantr["schemas"]["AuditEntry"];

/** A command's answer: carried out, with what the server answered, or refused, with each reason. */
export type Answer<R = Result> = { readonly outcome: "done"; readonly result: R } | Refusal;

/** A command that wasn't carried out: the status it was answered with (0 for none), and why. */
export interface Refusal {
  readonly outcome: "refused";
  readonly status: number;
  readonly reasons: readonly string[];
}

/** FastAPI's account of a body it couldn't validate. */
interface Invalid {
  readonly loc: readonly (string | number)[];
  readonly msg: string;
}

const isRecord = (value: unknown): value is Readonly<Record<string, unknown>> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/** Where in a command an invalid value is: its path after the command's own type. */
const at = (loc: Invalid["loc"]) => loc.slice(loc.indexOf("command") + 2).join(".");

/**
 * Each reason a refusal gives: a rejection's problems or its message, the body's errors, or a
 * refusal's `detail`, as a library's `HTTPException` gives it.
 */
function reasons(status: number, error: unknown): string[] {
  if (isRecord(error)) {
    const { detail, rejection } = error;
    if (Array.isArray(detail)) {
      return (detail as Invalid[]).map(({ loc, msg }) =>
        at(loc) === "" ? msg : `${at(loc)}: ${msg}`,
      );
    }
    if (typeof detail === "string") {
      return [detail];
    }
    if (isRecord(detail) && typeof detail.message === "string") {
      return [detail.message];
    }
    if (isRecord(rejection)) {
      const { errors, message } = rejection;
      return Array.isArray(errors) && errors.length > 0 ? errors.map(String) : [String(message)];
    }
  }
  return [`The server answered ${status}.`];
}

/** What openapi-fetch resolves with: the body, or the error's, and the response. */
interface Fetched<D> {
  readonly data?: D;
  readonly error?: unknown;
  readonly response: Response;
}

/**
 * The commands the UIs send over REST, over the given clients: reflexr's, and grantr's changes to
 * who may see and do what. `unsigned` is called when one is refused because no one is signed in,
 * as a read refused so ends the session.
 */
export function createCommands(api: Api, unsigned: () => void = () => {}) {
  /** A request's answer: `done` if the server says so of what it answered. */
  async function answer<D>(
    sent: Promise<Fetched<D>>,
    done: (data: D) => boolean = () => true,
  ): Promise<Answer<D>> {
    const answered = await sent.catch(() => null); // fetch throws when nothing answers
    if (answered === null) {
      return { outcome: "refused", status: 0, reasons: ["The server couldn't be reached."] };
    }
    const { data, error, response } = answered;
    if (data !== undefined && done(data)) {
      return { outcome: "done", result: data };
    }
    if (response.status === 401) {
      unsigned();
    }
    return {
      outcome: "refused",
      status: response.status,
      reasons: reasons(response.status, data ?? error),
    };
  }
  const tenantPath = (tenant: string) => ({ params: { path: { tenant } } });
  return {
    reflexr: {
      /** Send one command to a workspace, once: the same `id` makes a retry the same command. */
      send: (
        tenant: string,
        ws: string,
        command: Command,
        id: string = crypto.randomUUID(),
      ): Promise<Answer> =>
        answer(
          api.reflexr.POST("/workspaces/{workspace_id}/commands", {
            ...named(tenant),
            params: { path: { workspace_id: ws } },
            body: { type: "command", command_id: id, command },
          }),
          (result) => result.ok,
        ),
    },
    grantr: {
      /** Grant a role on a resource, such as a thread, to a member of the tenant. */
      grant: (tenant: string, request: GrantRequest): Promise<Answer<AuditEntry>> =>
        answer(
          api.grantr.POST("/grantr/v1/tenants/{tenant}/grants", {
            ...tenantPath(tenant),
            body: request,
          }),
        ),
      /** Take a grant back. */
      revoke: (tenant: string, request: GrantRequest): Promise<Answer<AuditEntry>> =>
        answer(
          api.grantr.POST("/grantr/v1/tenants/{tenant}/revocations", {
            ...tenantPath(tenant),
            body: request,
          }),
        ),
      /** Restrict a thread or artifact to those granted a role on it, or lift that. */
      restrict: (tenant: string, restriction: Restriction): Promise<Answer<AuditEntry>> =>
        answer(
          api.grantr.POST("/grantr/v1/tenants/{tenant}/restrictions", {
            ...tenantPath(tenant),
            body: restriction,
          }),
        ),
    },
  };
}
