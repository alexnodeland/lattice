import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { expect, test } from "vitest";
import { GENERATED, generate } from "../scripts/generate";

// The types are the packages' committed documents, as openapi-typescript and
// json-schema-to-typescript write them: `moon run client:types` regenerates them.
test("the generated types match the committed documents", async () => {
  for (const [name, text] of Object.entries(await generate())) {
    expect(await readFile(join(GENERATED, name), "utf8"), name).toBe(text);
  }
});
