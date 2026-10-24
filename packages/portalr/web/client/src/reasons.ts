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
const GENERIC = `Something went wrong.${AGAIN}`;

const CHANGED = `It changed while you were reading it.${AGAIN}`;
const STATE = "That can't be done as things stand.";
const FORBIDDEN = "You may not see this.";
/** What a refused command says of the reader not being allowed: it is an action, not a read. */
const NOT_ALLOWED = "You may not do this here.";
/** What values that aren't valid say, before where they are; ui's failure.ts says it too. */
const INVALID = "What was asked for isn't valid.";
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

/** What values that aren't valid say, with where they are, if known: "…isn't valid: a, b." */
export function invalidSaid(paths: readonly string[]): string {
  return paths.length > 0 ? `${INVALID.slice(0, -1)}: ${paths.join(", ")}.` : INVALID;
}

/**
 * The sentence a reader is told of a refusal, but where values aren't valid: by its reason code,
 * then its status, else the generic one. `acting` is for a command's refusal, whose reader wasn't
 * allowed to do something rather than to see it.
 */
export function sentenceOf(status: number, body: unknown, acting = false): string {
  const reason = REASONS.get(reasonOf(body) ?? "");
  const byStatus = status >= 500 ? `The server had a problem.${AGAIN}` : STATUSES.get(status);
  const read = reason ?? byStatus ?? GENERIC;
  return acting && read === FORBIDDEN ? NOT_ALLOWED : read;
}

/** Whether a refusal carries errors that may say where: FastAPI's list, or a rejection's. */
function located(body: unknown): boolean {
  return isRecord(body) && (Array.isArray(body.detail) || Array.isArray(typedOf(body).errors));
}

/**
 * The sentence a reader is told of a refusal, as `sentenceOf` says it; where it is of values that
 * aren't valid, with where they are. Reading where is rare, so it loads only then; if it can't
 * load, as offline, the sentence is said without where. It never rejects.
 */
export async function refusalSaid(status: number, body: unknown, acting = false): Promise<string> {
  const said = sentenceOf(status, body, acting);
  if (said !== INVALID || !located(body)) {
    return said;
  }
  try {
    const { invalidAt } = await import("./paths");
    return invalidSaid(invalidAt(body));
  } catch {
    return INVALID;
  }
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
