import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { build } from "vite";
import { afterAll, describe, expect, test } from "vitest";
import { notices } from "./plugin";
import type { Policy } from "./policy";
import { parseNotices } from "./render";

// These run the real `vite build` on a small project, to see what the bundler keeps.

const policy: Policy = { allowed: ["MIT", "ISC"], exceptions: [] };
const projects: string[] = [];
afterAll(() => {
  for (const project of projects) {
    rmSync(project, { recursive: true, force: true });
  }
});

/** A project whose entry imports `used`, imports and drops `shaken`, and two stylesheets' packages. */
function project(licences: Record<string, string> = {}): string {
  const root = mkdtempSync(join(tmpdir(), "notices-vite-"));
  projects.push(root);
  const install = (name: string, files: Record<string, string>, manifest = {}) => {
    const directory = join(root, "node_modules", name);
    mkdirSync(directory, { recursive: true });
    writeFileSync(
      join(directory, "package.json"),
      JSON.stringify({ name, version: "1.0.0", license: licences[name] ?? "MIT", ...manifest }),
    );
    for (const [file, text] of Object.entries({ LICENSE: `Licence of ${name}`, ...files })) {
      writeFileSync(join(directory, file), text);
    }
  };
  install("used", { "index.js": "export const used = () => 'used';" });
  // Imported but not used, from a package that says importing it does nothing: the bundler drops it.
  install(
    "shaken",
    { "index.js": "export const shaken = () => 'shaken';" },
    { sideEffects: false },
  );
  // A package of CSS alone, imported by the entry; and one only a stylesheet of ours imports.
  install("css-direct", { "style.css": ".direct { color: red }" });
  install("css-imported", { "style.css": ".imported { color: blue }" });
  mkdirSync(join(root, "src"));
  writeFileSync(
    join(root, "src", "style.css"),
    '@import "css-imported/style.css";\n.own { color: green }',
  );
  writeFileSync(
    join(root, "src", "main.js"),
    [
      "import { used } from 'used';",
      "import { shaken } from 'shaken';",
      "import 'css-direct/style.css';",
      "import './style.css';",
      "console.log(used());",
    ].join("\n"),
  );
  writeFileSync(join(root, "index.html"), '<script type="module" src="/src/main.js"></script>');
  return root;
}

async function built(root: string): Promise<string> {
  const result = await build({
    root,
    logLevel: "silent",
    configFile: false,
    build: { write: false },
    plugins: [notices({ ui: "fixture", policy })],
  });
  const outputs = (Array.isArray(result) ? result : [result]).flatMap((one) =>
    "output" in one ? one.output : [],
  );
  const file = outputs.find((output) => output.fileName === "THIRD-PARTY-NOTICES.txt");
  if (file?.type !== "asset" || typeof file.source !== "string") {
    throw new Error("the build wrote no notices");
  }
  return file.source;
}

describe("the plugin, in a real build", () => {
  test("names what the bundler kept: used code, and the stylesheets' packages, not what it dropped", async () => {
    const text = await built(project());
    expect(parseNotices(text).map((entry) => entry.name)).toEqual([
      "css-direct",
      "css-imported",
      "used",
    ]);
    expect(text).toContain("Licence of used");
    expect(text).not.toContain("shaken");
  });

  test("an election is said", async () => {
    const text = await built(project({ used: "(GPL-3.0-only OR ISC)" }));
    expect(text).toContain("Licence: (GPL-3.0-only OR ISC)\nUsed under: ISC\n");
  });

  test.each([
    ["used", "GPL-3.0-only"],
    ["css-direct", "MPL-2.0"],
    ["css-imported", "SEE LICENSE IN LICENSE"],
  ])("a disallowed %s (%s) fails the build, naming it", async (name, licence) => {
    await expect(built(project({ [name]: licence }))).rejects.toThrow(`${name}@1.0.0`);
  });

  test("a package that was dropped can have any licence", async () => {
    const text = await built(project({ shaken: "GPL-3.0-only" }));
    expect(text).not.toContain("shaken");
  });
});
