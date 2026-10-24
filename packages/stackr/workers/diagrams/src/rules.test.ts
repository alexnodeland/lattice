import { expect, test } from "vitest";
import { imagesRefused, servedPath, Warm } from "./rules";

test("a request names a file inside the page's directory, or none", () => {
  expect(servedPath("/index.html")).toBe("index.html");
  expect(servedPath("/fonts/Virgil/Virgil.woff2")).toBe("fonts/Virgil/Virgil.woff2");
  expect(servedPath("/../../etc/passwd")).toBe("etc/passwd");
  expect(servedPath("/%2e%2e/%2e%2e/etc/passwd")).toBe("etc/passwd");
  expect(servedPath("/%zz")).toBeUndefined();
  expect(servedPath("/a%00b")).toBeUndefined();
});

test("a render holds base64 PNGs and JPEGs, of the types its diagram names", () => {
  const named = { a: { media_type: "image/png" }, b: { media_type: "image/svg+xml" } };
  expect(imagesRefused({ a: "iVBORw0KGgo=" }, named)).toBeUndefined();
  expect(imagesRefused({ b: "PHN2Zy8+" }, named)).toContain("PNGs and JPEGs");
  expect(imagesRefused({ c: "AAAA" }, named)).toContain("image c is undefined");
  expect(imagesRefused({ a: "not base64!" }, named)).toContain("isn't base64");
  expect(imagesRefused({ a: 1 }, named)).toContain("isn't base64");
});

/** A warm thing whose making waits until let go, counting what it made and closed. */
function counted() {
  const made: number[] = [];
  const closed: number[] = [];
  let go: () => void = () => undefined;
  const warm = new Warm<number>(
    () =>
      new Promise((done) => {
        go = () => {
          made.push(made.length + 1);
          done(made.length);
        };
      }),
    (held) => !closed.includes(held),
    async (held) => {
      closed.push(held);
    },
  );
  return { warm, made, closed, release: () => go() };
}

test("one thing is made at a time, however many ask while it is made", async () => {
  const { warm, made, release } = counted();
  const first = warm.get();
  const second = warm.get();
  release();
  expect([await first, await second]).toEqual([1, 1]);
  expect(await warm.get()).toBe(1);
  expect(made).toEqual([1]);
});

test("one given up on while it is made is the next one's, not a second made behind it", async () => {
  const { warm, made, closed, release } = counted();
  const abandoned = warm.get();
  const discarded = warm.discard();
  release();
  await abandoned;
  await discarded;
  expect(closed).toEqual([1]);
  const next = warm.get();
  release();
  expect(await next).toBe(2);
  expect(made).toEqual([1, 2]);
});

test("a thing that died is made anew", async () => {
  const { warm, release } = counted();
  const first = warm.get();
  release();
  await first;
  await warm.discard();
  const again = warm.get();
  release();
  expect(await again).toBe(2);
});
