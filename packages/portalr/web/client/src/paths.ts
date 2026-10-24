/**
 * Where a refusal says values aren't valid, as the fields' paths a reader may be told (portalr
 * ADR-0070). It loads only when a refusal is of values that aren't valid: `refusalSaid` asks.
 */

// Its own, not reasons.ts's: importing that would split it out of the first load's chunk.
const isRecord = (value: unknown): value is Readonly<Record<string, unknown>> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/** What carries a refusal's errors: its rejection, if typed, else the body. */
const typedOf = (body: Readonly<Record<string, unknown>>) =>
  isRecord(body.detail) ? body.detail : isRecord(body.rejection) ? body.rejection : body;

/** Where in a request FastAPI says an error is, which isn't part of a field's path. */
const WHERE = new Set(["body", "query", "path", "header", "cookie"]);

/** A part of a field's path as a reader may see it: a name or an index, at most 32 long. */
const PART = /^[A-Za-z0-9_-]{1,32}$/u;

/** A part that names what may be a secret, or is shaped like one: its path isn't shown. */
const SECRET =
  /token|secret|passw|api[_-]?key|credential|bearer|authorization|^(sk|pk|rk|gh[pousr])[_-]/iu;

/** The most paths told, the most parts in each, and the most characters of them all. */
const MOST_PATHS = 5;
const MOST_PARTS = 6;
const MOST_SAID = 160;

/** Where in a `loc` a field's path starts: after a command frame's own parts, or where it is. */
function startOf(loc: readonly unknown[]): number {
  const command = loc.indexOf("command");
  if (command !== -1) {
    return command + 2;
  }
  return WHERE.has(String(loc[0])) ? 1 : 0;
}

/**
 * Where FastAPI's or Pydantic's errors say the values aren't valid: each error's `loc` as a dotted
 * path, from where `startOf` says. A path is told only if each of its parts is a plain name or
 * index of at most 32 characters, none of them secret-shaped, and it has at most six; at most
 * five paths are told, of at most 160 characters in all. So no text of the server's, nor a
 * secret it put in a key, comes through one.
 */
export function pathsOf(errors: unknown): string[] {
  if (!Array.isArray(errors)) {
    return [];
  }
  const paths = new Set<string>();
  let said = 0;
  for (const error of errors) {
    if (paths.size === MOST_PATHS) {
      break;
    }
    if (!(isRecord(error) && Array.isArray(error.loc))) {
      continue;
    }
    const loc: readonly unknown[] = error.loc;
    const parts = loc.slice(startOf(loc)).map(String);
    const shown =
      parts.length > 0 &&
      parts.length <= MOST_PARTS &&
      parts.every((part) => PART.test(part) && !SECRET.test(part));
    const path = parts.join(".");
    if (shown && !paths.has(path) && said + path.length <= MOST_SAID) {
      paths.add(path);
      said += path.length;
    }
  }
  return [...paths];
}

/** The paths a refusal says aren't valid: FastAPI's `detail` list, or a rejection's `errors`. */
export function invalidAt(body: unknown): string[] {
  if (!isRecord(body)) {
    return [];
  }
  return Array.isArray(body.detail) ? pathsOf(body.detail) : pathsOf(typedOf(body).errors);
}
