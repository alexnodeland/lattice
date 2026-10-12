import { expect, test } from "vitest";
import { sessionHeaders, streamUrl } from "./session";

test("a request carries the token: each read names its own tenant", () => {
  expect(sessionHeaders({ token: "t0k3n" })).toEqual({ Authorization: "Bearer t0k3n" });
});

test("with no one signed in, a request carries no token at all", () => {
  expect(sessionHeaders({ token: null })).toEqual({});
});

test("a stream carries the token and the tenant in its query, on the surface's scheme", () => {
  const session = { token: "t0k3n", tenant: "acme" };
  expect(streamUrl("https://app.example/artifactr/v1/", "ws 1", session)).toBe(
    "wss://app.example/artifactr/v1/workspaces/ws%201/stream?access_token=t0k3n&tenant=acme",
  );
  expect(streamUrl("http://localhost:8000/v1", "ws_1", session)).toMatch(
    /^ws:\/\/localhost:8000\//,
  );
});

test("a stream with no one signed in carries no token, which the server refuses", () => {
  expect(streamUrl("https://app.example/v1", "ws_1", { token: null, tenant: "acme" })).toBe(
    "wss://app.example/v1/workspaces/ws_1/stream?tenant=acme",
  );
});
