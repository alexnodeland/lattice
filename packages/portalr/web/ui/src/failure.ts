/**
 * What a failure says, as every screen shows it (lattice issue 552, portalr ADR-0065). A reader
 * sees a sentence of the kit's own, chosen by the refusal's status and its known reason code; no
 * words of the server's reach them, as they may hold what a tenant shouldn't read. The whole
 * failure is for operators: `failureLogged` writes it to the console, once, as one line, with
 * what looks like a secret taken out.
 */

const isRecord = (value: unknown): value is Readonly<Record<string, unknown>> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const AGAIN = " Try again in a moment.";

/** What any other failure says, such as one where the server couldn't be reached. */
export const GENERIC = `Something went wrong.${AGAIN}`;

const CHANGED = `It changed while you were reading it.${AGAIN}`;
const STATE = "That can't be done as things stand.";
const FORBIDDEN = "You may not see this.";
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
]);

/** What each status says, where no reason code a reader is told of came with it. */
const STATUSES = new Map<number, string>([
  [401, "You're not signed in. Sign in, then try again."],
  [403, FORBIDDEN],
  [404, NOT_FOUND],
  [422, INVALID],
  [429, `Too much was asked at once.${AGAIN}`],
]);

/** A refusal's reason code: its `detail`'s `type`, or its rejection's. */
function reasonOf(body: unknown): string | undefined {
  if (!isRecord(body)) {
    return undefined;
  }
  const typed = isRecord(body.detail) ? body.detail : body.rejection;
  return isRecord(typed) && typeof typed.type === "string" ? typed.type : undefined;
}

/**
 * The sentence a reader sees for a failure: by its reason code, then its status, else the
 * generic one. A refusal is anything with a numeric `status` and the body in `detail`, as the
 * client's `Refused` is.
 */
export function failureSaid(error: unknown): string {
  if (!isRecord(error) || typeof error.status !== "number") {
    return GENERIC;
  }
  const reason = REASONS.get(reasonOf(error.detail) ?? "");
  if (reason !== undefined) {
    return reason;
  }
  if (error.status >= 500) {
    return `The server had a problem.${AGAIN}`;
  }
  return STATUSES.get(error.status) ?? GENERIC;
}

/** The most graphemes of a failure's text the console line keeps. */
export const LONGEST = 2000;

/**
 * Format characters (direction marks, zero-width ones, tags), private-use and unassigned ones,
 * and blank fillers.
 */
const HIDDEN = new RegExp(`[\\p{Cf}\\p{Co}\\p{Cn}${String.fromCodePoint(0x3164, 0x2800)}]`, "gu");
/** The zero-width joiner, which joins an emoji's parts. */
const JOINER = String.fromCodePoint(0x200d);
/** Controls, separators and runs of space, which become one space. */
const BREAKS = /[\p{Cc}\p{Zl}\p{Zp}\s]+/gu;
/**
 * What looks like a secret: a URL's userinfo and query, a header's credentials, one given by
 * name, and tokens in their issuers' shapes.
 */
const SECRETS: readonly (readonly [RegExp, string])[] = [
  [/\b(\w{1,32}:\/\/)[^\s/@]{0,256}@/g, "$1"],
  [/\b(\w{1,32}:\/\/[^\s?#]{0,2048})[?#]\S*/g, "$1"],
  [/\b(authorization\s{0,8}[:=]\s{0,8}\w+)\s+\S+/gi, "$1 [redacted]"],
  [/\b(bearer|basic)\s+\S+/gi, "$1 [redacted]"],
  // A secret's word anywhere in a name, so a long name's or a run-together one's counts too.
  [
    /((?:token|secret|password|passwd|api[_-]?key)[\w-]{0,64}["']?\s{0,8}[:=]\s{0,8}["']?)[^\s"',}]+/gi,
    "$1[redacted]",
  ],
  // Tokens in their issuers' shapes: provider keys, GitHub's, and JWTs, as artifactr redacts them.
  [/\b(?:sk|pk|rk|key)-[\w-]{8,}/g, "[redacted]"],
  [/\b(?:gh[pousr]_\w{20,}|github_pat_\w{20,})/g, "[redacted]"],
  [/\beyJ[\w-]+\.eyJ[\w-]+\.[\w-]+/g, "[redacted]"],
];

/**
 * A failure's text as the console line keeps it: one line, nothing hidden, what looks like a
 * secret out, and no longer than `LONGEST` graphemes, cut between them.
 */
export function failureLine(error: unknown): string {
  // A joiner stays, so an emoji made of parts does.
  const whole = error instanceof Error ? error.message : String(error);
  let line = whole
    .replace(HIDDEN, (hidden) => (hidden === JOINER ? hidden : ""))
    .replace(BREAKS, " ")
    .trim();
  for (const [pattern, replacement] of SECRETS) {
    line = line.replace(pattern, replacement);
  }
  const graphemes = Array.from(new Intl.Segmenter().segment(line), ({ segment }) => segment);
  return graphemes.length > LONGEST ? `${graphemes.slice(0, LONGEST - 1).join("")}…` : line;
}

const logged = new WeakSet<object>();

/**
 * Writes a failure to the console, for operators, once each: call it from an effect, not a
 * render.
 */
export function failureLogged(error: unknown): void {
  if (typeof error === "object" && error !== null) {
    if (logged.has(error)) {
      return;
    }
    logged.add(error);
  }
  console.warn("A failure, for operators:", failureLine(error));
}
