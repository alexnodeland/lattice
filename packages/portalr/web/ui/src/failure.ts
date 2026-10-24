/**
 * What a failure says, as every screen shows it (lattice issue 552, portalr ADR-0065 and
 * ADR-0070). A reader sees a sentence of the kit's own, chosen by the refusal's status and its
 * known reason code, and where values aren't valid, the fields' paths; no words of the server's
 * reach them, as they may hold what a tenant shouldn't read. The whole failure, the server's
 * words included, goes to the console of the reader's own browser: `failureLogged` writes it
 * once, as one line, with what looks like a secret taken out.
 */

const isRecord = (value: unknown): value is Readonly<Record<string, unknown>> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/** What any other failure says, such as one where the server couldn't be reached. */
export const GENERIC = "Something went wrong. Try again in a moment.";

/** What values that aren't valid say, as the client's refusals say it too (its reasons.ts). */
export const INVALID = "What was asked for isn't valid.";

/**
 * The sentence a reader sees for a failure: a refused read's `said`, which the client chose by
 * its reason code and status (portalr ADR-0070), else the generic one. No words of the server's
 * are read here.
 */
export function failureSaid(error: unknown): string {
  return isRecord(error) && typeof error.said === "string" ? error.said : GENERIC;
}

/**
 * Why signing in was refused, in the kit's words: Supabase Auth's own message isn't shown
 * (portalr ADR-0070), and the whole error goes to the console.
 */
export function signInRefused(error: unknown): string {
  failureLogged(error);
  const record = isRecord(error) ? error : {};
  if (record.code === "invalid_credentials" || record.status === 400) {
    return "That email and password don't match an account.";
  }
  return record.status === 429 ? "Too many tries. Wait a moment, then try again." : GENERIC;
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
 * A failure whole, as text: an error's message, and a refusal's status and the server's body, as
 * JSON, which is where the server's own words are. Nothing of it is shown to the reader.
 */
function wholeOf(error: unknown): string {
  if (!isRecord(error)) {
    return String(error);
  }
  const message = error instanceof Error ? error.message : "";
  if (!("status" in error || "detail" in error)) {
    return message;
  }
  let detail: string;
  try {
    detail = JSON.stringify(error.detail) ?? "";
  } catch {
    detail = String(error.detail);
  }
  return `${message} status=${String(error.status)} detail=${detail}`;
}

/**
 * A failure's text as the console line keeps it: one line, nothing hidden, what looks like a
 * secret out, and no longer than `LONGEST` graphemes, cut between them.
 */
export function failureLine(error: unknown): string {
  // A joiner stays, so an emoji made of parts does.
  let line = wholeOf(error)
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
