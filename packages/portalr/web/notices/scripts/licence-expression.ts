// Fails unless the wheel's `license` expression (portalr's pyproject.toml) lists exactly the
// licences it is under: its own, and those the bundled packages are used under, read from the
// notices the two UIs' builds wrote.
import { readFileSync } from "node:fs";
import { bundledLicences, expressionProblems, parseNotices } from "../src/index";

const root = new URL("../../../", import.meta.url);
const entries = ["app", "admin"].flatMap((ui) =>
  parseNotices(
    readFileSync(new URL(`src/portalr/static/${ui}/THIRD-PARTY-NOTICES.txt`, root), "utf8"),
  ),
);
const project = Bun.TOML.parse(readFileSync(new URL("pyproject.toml", root), "utf8")) as {
  project: { license: string };
};
const bundled = bundledLicences(entries);
const problems = expressionProblems(project.project.license, bundled);
for (const problem of problems) {
  process.stderr.write(`notices: ${problem}\n`);
}
if (problems.length > 0) {
  process.exit(1);
}
process.stdout.write(
  `notices: the license expression covers ${bundled.join(", ")} and portalr's own\n`,
);
