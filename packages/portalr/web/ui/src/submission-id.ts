/**
 * A submission's id, derived as artifactr.ui derives it (lattice RFC-0005), so a retried submit is
 * the same artifact and the server's check can work the id out again: `sub_` and the first 32 hex
 * digits of the SHA-256 of the parts joined by NUL, which no id can hold. The parts are the form's
 * policy and its id, then the person's principal for a form answered once a person, or the
 * submit's own nonce for one answered any number of times; a form answered once has no more. The
 * policy is part of the id, so a form whose policy changed never takes an earlier submission's id.
 */

/** What makes a submission its own, beyond its form: nothing, the person, or the submit. */
export type Whose =
  | { readonly submissions: "once" }
  | { readonly submissions: "per_person"; readonly principal: string }
  | { readonly submissions: "many"; readonly nonce: string };

const parts = (formId: string, whose: Whose): readonly string[] => {
  switch (whose.submissions) {
    case "once":
      return ["once", formId];
    case "per_person":
      return ["per_person", formId, whose.principal];
    case "many":
      return ["many", formId, whose.nonce];
    default:
      return whose satisfies never;
  }
};

/** The id of a submission to `formId`, whose own it is as `whose` says. */
export async function submissionId(formId: string, whose: Whose): Promise<string> {
  const bytes = new TextEncoder().encode(parts(formId, whose).join("\0"));
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  const hex = Array.from(digest, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return `sub_${hex.slice(0, 32)}`;
}

/** A person's principal, as artifactr keys whoever acts for a person: `user:` and their id. */
export const principalOf = (person: string) => `user:${person}`;
