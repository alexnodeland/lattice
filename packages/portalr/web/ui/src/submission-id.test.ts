import { expect, test } from "vitest";
import SUBMISSION_IDS from "../../../../artifactr/tests/ui/vectors/submission_ids.json";
import { principalOf, submissionId, type Whose } from "./submission-id";

/** The ids artifactr.ui derives, from the vectors it commits. */
const VECTORS = SUBMISSION_IDS.cases;

const whose = (vector: (typeof VECTORS)[number]): Whose => {
  if ("principal" in vector) {
    return { submissions: "per_person", principal: vector.principal };
  }
  if ("nonce" in vector) {
    return { submissions: "many", nonce: vector.nonce };
  }
  return { submissions: "once" };
};

test.each(VECTORS)("a submission to $form_id is $id, as the package derives it", async (vector) => {
  expect(await submissionId(vector.form_id, whose(vector))).toBe(vector.id);
});

test("a person's principal is artifactr's key for whoever acts for them", () => {
  expect(principalOf("alice")).toBe("user:alice");
});
