import { QueryClient } from "@tanstack/react-query";
import type { Server } from "bun";
import { afterAll, beforeAll, expect, test } from "vitest";
import { models } from "./models";
import { type Api, createApi } from "./rest";

const MODELS = [
  { id: "default", label: "Default", family: "", local: false, reasoning: false },
  { id: "deep", label: "Deep", family: "anthropic", local: false, reasoning: true },
];

const asked: { readonly url: URL; readonly headers: Headers }[] = [];
let server: Server<unknown>;
let api: Api;

beforeAll(() => {
  server = Bun.serve({
    port: 0,
    fetch(request) {
      const url = new URL(request.url);
      asked.push({ url, headers: request.headers });
      if (request.headers.get("x-tenant") === "refused") {
        return Response.json({ detail: { type: "forbidden", message: "no" } }, { status: 403 });
      }
      return Response.json({ models: MODELS });
    },
  });
  const origin = `http://127.0.0.1:${server.port}`;
  api = createApi(
    { artifactr: `${origin}/artifactr/v1`, reflexr: `${origin}/reflexr/v1`, grantr: origin },
    () => ({ token: "t0k3n" }),
  );
});

afterAll(() => {
  server.stop(true);
});

test("the models are asked for in a tenant's workspace, with the session", async () => {
  const listed = await new QueryClient().fetchQuery(models(api, "acme", "main"));
  expect(listed).toEqual(MODELS);
  const request = asked.at(-1);
  expect(request?.url.pathname).toBe("/portalr/v1/models");
  expect(request?.url.searchParams.get("workspace")).toBe("main");
  expect(request?.headers.get("x-tenant")).toBe("acme");
  expect(request?.headers.get("authorization")).toBe("Bearer t0k3n");
});

test("each workspace's models are kept apart, under the tenant's key", () => {
  expect(models(api, "acme", "main").queryKey).toEqual(["portalr", "acme", "models", "main"]);
  expect(models(api, "acme", "main").queryKey).not.toEqual(models(api, "acme", "x").queryKey);
});

test("a refusal is a refusal, not tried again", async () => {
  const before = asked.length;
  const reading = new QueryClient().fetchQuery(models(api, "refused", "main"));
  await expect(reading).rejects.toThrow("the models couldn't be read");
  expect(asked.length - before).toBe(1);
});
