/**
 * Why the server refused a request, as people read it, for a command and a read alike: a
 * rejection's problems or its message, FastAPI's errors in the body, or a refusal's `detail`, as
 * a library's `HTTPException` gives it; never the body as it came.
 */

interface Invalid {
  readonly loc: readonly (string | number)[];
  readonly msg: string;
}

const isRecord = (value: unknown): value is Readonly<Record<string, unknown>> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/**
 * Where in a body an invalid value is. FastAPI's path starts at `body`; in a command frame it runs
 * on through `command` and the command's own type, `["body", "command", "install_rule", "rule"]`,
 * which say nothing a person typed, so the path starts after them. Elsewhere it starts after
 * `body`. The body itself, or the command, is an empty path.
 */
function at(loc: Invalid["loc"]): string {
  const command = loc.indexOf("command");
  return (command === -1 ? loc.slice(1) : loc.slice(command + 2)).join(".");
}

/**
 * Each reason a refusal gives: a rejection's problems or its message, the body's errors, or a
 * refusal's `detail`, as a library's `HTTPException` gives it.
 */
export function reasons(status: number, error: unknown): string[] {
  if (isRecord(error)) {
    const { detail, rejection } = error;
    if (Array.isArray(detail)) {
      return (detail as Invalid[]).map(({ loc, msg }) => {
        const path = at(loc);
        return path === "" ? msg : `${path}: ${msg}`;
      });
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
