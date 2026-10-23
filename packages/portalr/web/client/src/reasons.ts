/**
 * Why the server refused a request, as people read it, for a command and a read alike (lattice
 * issue 552, portalr ADR-0070). A reader is told a sentence of the kit's own, chosen by the
 * refusal's known reason code, else its status; where the refusal is of values that aren't valid,
 * also where they are, as the fields' paths. No words of the server's reach them: its messages
 * and its `detail` text may hold what a tenant shouldn't read. The whole body is for operators,
 * whom the UIs' console line tells.
 */

const isRecord = (value: unknown): value is Readonly<Record<string, unknown>> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const AGAIN = " Try again in a moment.";

/** What any other refusal says, such as one where the server couldn't be reached. */
export const GENERIC = `Something went wrong.${AGAIN}`;

const CHANGED = `It changed while you were reading it.${AGAIN}`;
const STATE = "That can't be done as things stand.";
const FORBIDDEN = "You may not see this.";
/** What a refused command says of the reader not being allowed: it is an action, not a read. */
const NOT_ALLOWED = "You may not do this here.";
/** What values that aren't valid say, before where they are. */
export const INVALID = "What was asked for isn't valid.";
const NOT_FOUND = "It isn't there: it may have been moved or archived.";

/** What each reason code a refusal may carry says, in plain words. */
const REASONS = new Map<string, string>([
  ["forbidden", FORBIDDEN],
  ["not_found", NOT_FOUND],
  ["not_enabled", "This is switched off for this workspace. Ask an admin to switch it on."],
  ["invalid_state", STATE],
  ["version_conflict", CHANGED],
  ["validation_failed", INVALID],
  ["over_quota", "There's no room left here."],
  ["too_slow", "It arrived too slowly."],
  ["artifact_busy", "Someone else has it now."],
  ["invite_failed", "The invitation wasn't sent: check the email."],
]);

/** What each status says, where no reason code a reader is told of came with it. */
const STATUSES = new Map<number, string>([
  [401, "You're not signed in. Sign in, then try again."],
  [403, FORBIDDEN],
  [404, NOT_FOUND],
  [413, "That's too large."],
  [422, INVALID],
  [429, `Too much was asked at once.${AGAIN}`],
]);

/** What carries a refusal's reason: its `detail` or its rejection, if typed, else the body. */
function typedOf(body: Readonly<Record<string, unknown>>): Readonly<Record<string, unknown>> {
  if (isRecord(body.detail)) {
    return body.detail;
  }
  return isRecord(body.rejection) ? body.rejection : body;
}

/** A refusal's reason code: its `detail`'s `type`, or its rejection's. */
function reasonOf(body: unknown): string | undefined {
  if (!isRecord(body)) {
    return undefined;
  }
  const { type } = typedOf(body);
  return typeof type === "string" ? type : undefined;
}

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

/** What values that aren't valid say, with where they are, if known: "…isn't valid: a, b." */
export function invalidSaid(paths: readonly string[]): string {
  return paths.length > 0 ? `${INVALID.slice(0, -1)}: ${paths.join(", ")}.` : INVALID;
}

/** The paths a refusal says aren't valid: FastAPI's `detail` list, or a rejection's `errors`. */
function invalidAt(body: unknown): string[] {
  if (!isRecord(body)) {
    return [];
  }
  return Array.isArray(body.detail) ? pathsOf(body.detail) : pathsOf(typedOf(body).errors);
}

/**
 * The sentence a reader is told of a refusal: by its reason code, then its status, else the
 * generic one; where it is of values that aren't valid, with where they are. `acting` is for a
 * command's refusal, whose reader wasn't allowed to do something rather than to see it.
 */
export function refusalSaid(status: number, body: unknown, acting = false): string {
  const reason = REASONS.get(reasonOf(body) ?? "");
  const byStatus = status >= 500 ? `The server had a problem.${AGAIN}` : STATUSES.get(status);
  const read = reason ?? byStatus ?? GENERIC;
  const said = acting && read === FORBIDDEN ? NOT_ALLOWED : read;
  return said === INVALID ? invalidSaid(invalidAt(body)) : said;
}

/** Each reason a command's refusal gives, as its sender is told it: one sentence of the kit's own. */
export function reasons(status: number, body: unknown): string[] {
  return [refusalSaid(status, body, true)];
}

/**
 * A reason run on after a colon, as `refusal` and a file's check-out say them: its first letter
 * in lower case, where its first word is an ordinary one ("You", "Someone", "The"), and as it is
 * where it is a name with capitals of its own ("WordCraft") or an initialism ("OK").
 */
export function runOn(reason: string): string {
  return /^[A-Z][a-z']*\b/u.test(reason) && !/^[A-Z][a-z']*[A-Z]/u.test(reason)
    ? reason.charAt(0).toLowerCase() + reason.slice(1)
    : reason;
}
