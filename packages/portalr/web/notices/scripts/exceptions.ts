// Fails when policy.json holds an exception that no package in either UI's bundle needs. It reads
// the notices the two builds wrote, which name every package bundled and its declared licence.
import { readFileSync } from "node:fs";
import { parseNotices, readPolicy, staleExceptions } from "../src/index";

const policy = readPolicy(new URL("../policy.json", import.meta.url));
const bundled = ["app", "admin"].flatMap((ui) =>
  parseNotices(
    readFileSync(
      new URL(`../../../src/portalr/static/${ui}/THIRD-PARTY-NOTICES.txt`, import.meta.url),
      "utf8",
    ),
  ),
);
const stale = staleExceptions(bundled, policy);
for (const { package: name, message } of stale) {
  process.stderr.write(`notices: ${name}: ${message}\n`);
}
if (stale.length > 0) {
  process.exit(1);
}
process.stdout.write(
  `notices: ${policy.exceptions.length} exceptions, each needed, over ${bundled.length} bundled packages\n`,
);
