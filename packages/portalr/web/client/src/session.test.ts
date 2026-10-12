import { expect, test } from "vitest";
import { sessionHeaders, streamUrl } from "./session";

test("a request carries the token, and no tenant: each read names its own", () => {
  expect(sessionHeaders({ token: "t0k3n", tenant: "acme" })).toEqual({
    Authorization: "Bearer t0k3n",
  });
});

test("with no one signed in, a request carries no token at all", () => {
  expect(sessionHeaders({ token: null, tenant: null })).toEqual({});
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
