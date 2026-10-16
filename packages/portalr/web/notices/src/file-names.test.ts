import { readFileSync } from "node:fs";
import { expect, test } from "vitest";
import { isLicenceFile, isNoticeFile } from "./collect";

// The table is shared with portalr's tests of scripts/check_wheel.py, which holds the same
// reading of a licence file in Python: both run these cases, so they can't drift apart.
const names = JSON.parse(readFileSync(new URL("../file-names.json", import.meta.url), "utf8")) as {
  licence: string[];
  notice: string[];
  neither: string[];
};

test.each(names.licence)("%s is a licence text", (file) => {
  expect(isNoticeFile(file)).toBe(true);
  expect(isLicenceFile(file)).toBe(true);
});

test.each(names.notice)("%s is collected but is not a licence text", (file) => {
  expect(isNoticeFile(file)).toBe(true);
  expect(isLicenceFile(file)).toBe(false);
});

test.each(names.neither)("%s is not collected", (file) => {
  expect(isNoticeFile(file)).toBe(false);
});
