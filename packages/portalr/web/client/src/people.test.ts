import { QueryClient } from "@tanstack/react-query";
import type { Server } from "bun";
import { afterAll, beforeAll, expect, test } from "vitest";
import { namesOf, shortId } from "./people";
import { createQueries, keys, PEOPLE_MAX, Refused } from "./queries";
import { createApi } from "./rest";

const UUID = "3f2a91c4-1111-4222-8333-444455556666";

const asked: { readonly url: URL; readonly headers: Headers }[] = [];
let server: Server<unknown>;
let queries: ReturnType<typeof createQueries>;

beforeAll(() => {
  server = Bun.serve({
    port: 0,
    fetch(request) {
      const url = new URL(request.url);
      asked.push({ url, headers: request.headers });
      if (request.headers.get("x-tenant") === "refused") {
        return Response.json({ detail: { type: "forbidden", message: "no" } }, { status: 403 });
      }
      const people = Object.fromEntries(
        url.searchParams
          .getAll("id")
          .filter((id) => !id.startsWith("ghost"))
          .map((id) => [id, `${id}@acme.test`]),
      );
      return Response.json({ people });
    },
  });
  const origin = `http://127.0.0.1:${server.port}`;
  queries = createQueries(
    createApi(
      { artifactr: `${origin}/artifactr/v1`, reflexr: `${origin}/reflexr/v1`, grantr: origin },
      () => ({ token: "t0k3n" }),
    ),
  );
});

afterAll(() => {
  server.stop(true);
});

test("a long id is cut to its first eight characters, a short one is kept", () => {
  expect(shortId(UUID)).toBe("3f2a91c4…");
  expect(shortId("alice")).toBe("alice");
  expect(shortId("0123456789abcde")).toBe("0123456789abcde");
  expect(shortId("0123456789abcdef")).toBe("01234567…");
});

test("a person is named by their email where it is known, else by a short id", () => {
  const names = namesOf({ [UUID]: "ada@acme.test" });
  expect(names(UUID)).toBe("ada@acme.test");
  expect(names("c0ffee00-1111-4222-8333-444455556666")).toBe("c0ffee00…");
  expect(namesOf(undefined)(UUID)).toBe("3f2a91c4…");
});

test("the emails are asked for in a tenant, by id, with the session", async () => {
  const emails = await new QueryClient().fetchQuery(queries.portalr.people("acme", ["a1", "b2"]));
  expect(emails).toEqual({ a1: "a1@acme.test", b2: "b2@acme.test" });
  const request = asked.at(-1);
  expect(request?.url.pathname).toBe("/portalr/v1/people");
  expect(request?.url.searchParams.getAll("id")).toEqual(["a1", "b2"]);
  expect(request?.headers.get("x-tenant")).toBe("acme");
  expect(request?.headers.get("authorization")).toBe("Bearer t0k3n");
  expect(request?.url.href).not.toContain("@");
});

test("an operator asks with no tenant", async () => {
  await new QueryClient().fetchQuery(queries.portalr.people(null, ["a1"]));
  expect(asked.at(-1)?.headers.has("x-tenant")).toBe(false);
});

test("more than the server takes in one request are asked for in several", async () => {
  const ids = Array.from({ length: PEOPLE_MAX + 5 }, (_, index) => `u${index}`);
  const before = asked.length;
  const emails = await new QueryClient().fetchQuery(queries.portalr.people("acme", ids));
  expect(Object.keys(emails)).toHaveLength(ids.length);
  const sent = asked.slice(before).map((each) => each.url.searchParams.getAll("id").length);
  expect(sent).toEqual([PEOPLE_MAX, 5]);
});

test("an id the server leaves out is left out of the answer", async () => {
  const emails = await new QueryClient().fetchQuery(
    queries.portalr.people("acme", ["a1", "ghost-1"]),
  );
  expect(emails).toEqual({ a1: "a1@acme.test" });
});

test("a refused read throws, for the screen to fall back on short ids", async () => {
  await expect(
    new QueryClient().fetchQuery(queries.portalr.people("refused", ["a1"])),
  ).rejects.toBeInstanceOf(Refused);
});

test("the read is kept for a few minutes in memory, once for one set of ids, and not tried again", () => {
  const options = queries.portalr.people("acme", ["a1"]);
  expect(options.queryKey).toEqual(keys.portalr.people("acme", ["a1"]));
  expect(options.retry).toBe(false);
  expect(options.staleTime).toBe(5 * 60_000);
  expect(options.gcTime).toBe(5 * 60_000);
  expect(options.refetchOnWindowFocus).toBe(false);
  expect(keys.portalr.people(null, ["a1"])).not.toEqual(keys.portalr.people("acme", ["a1"]));
});
