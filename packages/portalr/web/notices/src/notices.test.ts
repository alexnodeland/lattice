import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, describe, expect, test } from "vitest";
import { collect, declaredLicence, packageDirectory } from "./collect";
import { check, type Policy, readPolicy, staleExceptions } from "./policy";
import { parseNotices, render } from "./render";

const root = mkdtempSync(join(tmpdir(), "notices-"));
afterAll(() => rmSync(root, { recursive: true, force: true }));

/** A package in a fixture node_modules, with these manifest fields and these files. */
function pack(
  name: string,
  manifest: Record<string, unknown>,
  files: Record<string, string> = { LICENSE: `The licence of ${name}.\n` },
): string {
  const directory = join(root, "node_modules", name);
  mkdirSync(directory, { recursive: true });
  writeFileSync(
    join(directory, "package.json"),
    JSON.stringify({ name, version: "1.0.0", ...manifest }),
  );
  for (const [file, text] of Object.entries(files)) {
    writeFileSync(join(directory, file), text);
  }
  return join(directory, "index.js");
}

const policy: Policy = { allowed: ["MIT", "ISC", "Apache-2.0"], exceptions: [] };
const problemsOf = (ids: string[], using: Policy = policy) =>
  check(collect(ids), using).map((p) => `${p.package}: ${p.message}`);

describe("which packages are bundled", () => {
  test("a module is in the package of the last node_modules in its path", () => {
    expect(packageDirectory("/a/node_modules/.bun/x@1/node_modules/x/dist/i.js")).toBe(
      "/a/node_modules/.bun/x@1/node_modules/x",
    );
    expect(packageDirectory("/a/node_modules/@scope/pkg/i.js?v=1")).toBe(
      "/a/node_modules/@scope/pkg",
    );
    expect(packageDirectory("/a/web/ui/src/button.tsx")).toBeUndefined();
  });

  test("lattice's own modules and virtual ones are no package, and each package counts once", () => {
    const react = pack("react", { license: "MIT" });
    const found = collect([
      react,
      `${react}?x`,
      join(root, "node_modules/react/other.js"),
      "/a/src/x.tsx",
      "\0virtual",
    ]);
    expect(found.map((p) => p.name)).toEqual(["react"]);
  });

  test("a licence is declared as a string, an object, or a list of them", () => {
    expect(declaredLicence({ license: "MIT" })).toBe("MIT");
    expect(declaredLicence({ license: { type: "ISC" } })).toBe("ISC");
    expect(declaredLicence({ licenses: [{ type: "MIT" }, { type: "Apache-2.0" }] })).toBe(
      "(MIT OR Apache-2.0)",
    );
    expect(declaredLicence({})).toBeUndefined();
    expect(declaredLicence({ license: "  " })).toBeUndefined();
    expect(declaredLicence({ licenses: [{ type: "MIT" }, {}] })).toBeUndefined();
  });
});

describe("the policy", () => {
  test("allowed licences, and an expression of them, pass", () => {
    const ids = [
      pack("a-mit", { license: "MIT" }),
      pack("b-and", { license: "MIT AND ISC" }),
      pack("c-or", { license: "(MIT OR GPL-3.0-only)" }),
      pack("d-list", { licenses: [{ type: "ISC" }, { type: "GPL-2.0-only" }] }),
    ];
    expect(problemsOf(ids)).toEqual([]);
  });

  test("a licence that isn't allowed fails, copyleft or not", () => {
    const ids = [
      pack("gpl", { license: "GPL-3.0-only" }),
      pack("mpl", { license: "MPL-2.0" }),
      pack("both", { license: "MIT AND LGPL-3.0-or-later" }),
      pack("blue", { license: "Zlib" }),
    ];
    expect(problemsOf(ids)).toEqual([
      "blue@1.0.0: its licence, Zlib, isn't allowed",
      "both@1.0.0: its licence, MIT AND LGPL-3.0-or-later, isn't allowed",
      "gpl@1.0.0: its licence, GPL-3.0-only, isn't allowed",
      "mpl@1.0.0: its licence, MPL-2.0, isn't allowed",
    ]);
  });

  test("a missing licence, or one that isn't SPDX, fails", () => {
    const ids = [
      pack("none", {}),
      pack("see", { license: "SEE LICENSE IN LICENSE.md" }),
      pack("unlicensed", { license: "UNLICENSED" }),
    ];
    expect(problemsOf(ids)).toEqual([
      "none@1.0.0: declares no licence",
      "see@1.0.0: its licence, SEE LICENSE IN LICENSE.md, isn't an SPDX expression",
      "unlicensed@1.0.0: its licence, UNLICENSED, isn't allowed",
    ]);
  });

  test("a package that ships no licence text fails, whatever it declares", () => {
    expect(problemsOf([pack("bare", { license: "MIT" }, { "README.md": "hi" })])).toEqual([
      "bare@1.0.0: ships no LICENSE, COPYING or NOTICE file",
    ]);
  });

  test("a vendored package's licence, beside the modules bundled from it, is the text it ships", () => {
    const vendor = pack("vendor", { license: "MIT AND ISC" }, { "README.md": "no licence here" });
    const nested = join(root, "node_modules", "vendor", "lib-vendor", "d3-thing");
    mkdirSync(nested, { recursive: true });
    writeFileSync(join(nested, "LICENSE"), "ISC licence of d3-thing");
    writeFileSync(join(nested, "index.js"), "");
    writeFileSync(join(root, "node_modules", "vendor", "lib-vendor", "unused.js"), "");
    expect(problemsOf([vendor])).toEqual([
      "vendor@1.0.0: ships no LICENSE, COPYING or NOTICE file",
    ]);
    const found = collect([join(nested, "index.js")]);
    expect(found[0]?.texts).toEqual([
      { file: join("lib-vendor", "d3-thing", "LICENSE"), text: "ISC licence of d3-thing" },
    ]);
    expect(check(found, policy)).toEqual([]);
  });

  test("an exception covers a package and exactly the licence it names", () => {
    const ids = [pack("odd", { license: "MPL-2.0" })];
    const exception = {
      package: "odd",
      licence: "MPL-2.0",
      kind: "licence" as const,
      reason: "reviewed: only linked, unmodified",
    };
    expect(problemsOf(ids, { ...policy, exceptions: [exception] })).toEqual([]);
    // The package moved to another licence: the exception no longer applies.
    const moved = [pack("odd", { license: "GPL-3.0-only" })];
    expect(problemsOf(moved, { ...policy, exceptions: [exception] })).toEqual([
      "odd@1.0.0: its licence, GPL-3.0-only, isn't allowed",
    ]);
  });

  test("a licence exception doesn't excuse missing text, nor a text exception a bad licence", () => {
    const ids = [pack("odd2", { license: "MPL-2.0" }, {})];
    const licence = {
      package: "odd2",
      licence: "MPL-2.0",
      kind: "licence" as const,
      reason: "reviewed",
    };
    const text = { ...licence, kind: "text" as const };
    expect(problemsOf(ids, { ...policy, exceptions: [licence] })).toEqual([
      "odd2@1.0.0: ships no LICENSE, COPYING or NOTICE file",
    ]);
    expect(problemsOf(ids, { ...policy, exceptions: [text] })).toEqual([
      "odd2@1.0.0: its licence, MPL-2.0, isn't allowed",
    ]);
    expect(problemsOf(ids, { ...policy, exceptions: [licence, text] })).toEqual([]);
  });

  test("a package excused for its missing text says why in the notices", () => {
    const ids = [pack("shim", { license: "MIT" }, {})];
    const text = {
      package: "shim",
      licence: "MIT",
      kind: "text" as const,
      reason: "A shim over d3.",
    };
    const found = collect(ids);
    expect(check(found, { ...policy, exceptions: [text] })).toEqual([]);
    const notices = render("app", found, new Map([["shim@1.0.0", text.reason]]));
    expect(notices).toContain("This package ships no licence text. A shim over d3.");
    expect(parseNotices(notices)).toEqual([
      { name: "shim", version: "1.0.0", licence: "MIT", hasText: false },
    ]);
  });

  test("an exception that no bundled package needs is stale", () => {
    const reviewed = { licence: "MPL-2.0", kind: "licence" as const, reason: "reviewed" };
    const mit = { licence: "MIT", reason: "reviewed" };
    const stale = staleExceptions(
      [
        { name: "odd", licence: "MPL-2.0", hasText: true },
        { name: "moved", licence: "GPL-3.0-only", hasText: true },
        { name: "fine", licence: "MIT", hasText: true },
        { name: "bare", licence: "MIT", hasText: false },
        { name: "texty", licence: "MIT", hasText: true },
      ],
      {
        ...policy,
        exceptions: [
          { ...reviewed, package: "odd" },
          { ...reviewed, package: "gone" },
          { ...reviewed, package: "moved" },
          { ...mit, kind: "licence", package: "fine" },
          { ...mit, kind: "text", package: "bare" },
          { ...mit, kind: "text", package: "texty" },
        ],
      },
    );
    expect(stale.map((p) => p.package)).toEqual(["gone", "moved", "fine", "texty"]);
  });

  test("policy.json is well formed, and is the user's list", () => {
    const real = readPolicy(new URL("../policy.json", import.meta.url));
    expect(real.allowed).toEqual([
      "0BSD",
      "Apache-2.0",
      "BSD-2-Clause",
      "BSD-3-Clause",
      "BlueOak-1.0.0",
      "CC0-1.0",
      "ISC",
      "MIT",
      "Python-2.0",
      "Unlicense",
    ]);
    const bad = join(root, "bad.json");
    writeFileSync(
      bad,
      JSON.stringify({
        allowed: ["MIT"],
        exceptions: [{ package: "x", licence: "GPL-3.0-only", kind: "licence", reason: " " }],
      }),
    );
    expect(() => readPolicy(bad)).toThrow("with a reason");
    writeFileSync(bad, JSON.stringify({ allowed: "MIT", exceptions: [] }));
    expect(() => readPolicy(bad)).toThrow("list of SPDX identifiers");
  });
});

describe("the notices file", () => {
  const ids = [
    pack(
      "zeta",
      { license: "Apache-2.0", repository: { url: "git+https://example.com/zeta.git" } },
      {
        LICENSE: "Apache licence text\r\n",
        NOTICE: "Zeta\nCopyright 2026 Zeta authors\n",
        "README.md": "not a notice",
      },
    ),
    pack("alpha", { license: "MIT AND ISC", homepage: "https://example.com/alpha" }),
    pack("@s/mid", { license: "ISC" }, { "LICENSE.md": "mid licence", "COPYING-extra": "more" }),
  ];

  test("names each package once, sorted, with its licence and every notice text", () => {
    const text = render("app", collect(ids));
    expect(parseNotices(text)).toEqual([
      { name: "@s/mid", version: "1.0.0", licence: "ISC", hasText: true },
      { name: "alpha", version: "1.0.0", licence: "MIT AND ISC", hasText: true },
      { name: "zeta", version: "1.0.0", licence: "Apache-2.0", hasText: true },
    ]);
    expect(text).toContain("Source: https://example.com/zeta.git");
    expect(text).toContain("Source: https://example.com/alpha");
    expect(text).toContain("--- NOTICE\n\nZeta\nCopyright 2026 Zeta authors");
    expect(text).toContain("--- LICENSE\n\nApache licence text\n");
    expect(text).not.toContain("\r");
    expect(text).not.toContain("not a notice");
    expect(text).toContain("--- COPYING-extra");
  });

  test("is the same however the bundle lists its modules, with no date in it", () => {
    const first = render("app", collect(ids));
    const second = render("app", collect([...ids].reverse()));
    expect(second).toBe(first);
    expect(first).not.toMatch(/20\d\d-\d\d-\d\d|\d\d:\d\d:\d\d/);
  });
});
