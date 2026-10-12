/**
 * Commands sent over a library's REST rather than its stream, for an answer to every one.
 *
 * A stream answers a command it can't read with an error frame that names no command, so a
 * command typed by hand, such as a rule's JSON, would never settle there. Its REST route answers
 * each request: carried out, refused with the library's rejection, or refused by FastAPI's
 * validation when the body isn't a command at all (portalr ADR-0020).
 */

import type { components } from "./generated/reflexr.openapi";
import type { Api } from "./rest";

type Command = components["schemas"]["Command"];
type Result = components["schemas"]["CommandResult"];

/** A command's answer: carried out, or refused, with each reason in words. */
export type Answer =
  | { readonly outcome: "done"; readonly result: Result }
  | { readonly outcome: "refused"; readonly status: number; readonly reasons: readonly string[] };

/** FastAPI's account of a body it couldn't validate. */
interface Invalid {
  readonly loc: readonly (string | number)[];
  readonly msg: string;
}

/** Where in a command an invalid value is: its path after the command's own type. */
const at = (loc: Invalid["loc"]) => loc.slice(loc.indexOf("command") + 2).join(".");

/** Each reason a refusal gives: a rejection's problems, or its message, or the body's errors. */
function reasons(status: number, error: unknown): string[] {
  if (typeof error !== "object" || error === null) {
    return [`The server answered ${status}.`];
  }
  if ("detail" in error && Array.isArray(error.detail)) {
    return (error.detail as Invalid[]).map(({ loc, msg }) =>
      at(loc) === "" ? msg : `${at(loc)}: ${msg}`,
    );
  }
  if ("rejection" in error && typeof error.rejection === "object" && error.rejection !== null) {
    const { errors, message } = error.rejection as { errors?: unknown; message?: unknown };
    if (Array.isArray(errors) && errors.length > 0) {
      return errors.map(String);
    }
    return [String(message)];
  }
  return [`The server answered ${status}.`];
}

/** The commands the UIs send over REST, over the given clients. */
export function createCommands(api: Api) {
  return {
    reflexr: {
      /** Send one command to a workspace, once: `id` makes a retry of it the same command. */
      send: async (tenant: string, ws: string, command: Command, id: string): Promise<Answer> => {
        const { data, error, response } = await api.reflexr.POST(
          "/workspaces/{workspace_id}/commands",
          {
            headers: { "X-Tenant": tenant },
            params: { path: { workspace_id: ws } },
            body: { type: "command", command_id: id, command },
          },
        );
        if (data?.ok === true) {
          return { outcome: "done", result: data };
        }
        return {
          outcome: "refused",
          status: response.status,
          reasons: reasons(response.status, data ?? error),
        };
      },
    },
  };
}
