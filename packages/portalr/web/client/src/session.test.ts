import { expect, test } from "vitest";
import { sessionHeaders, streamUrl } from "./session";

const session = { token: "t0k3n", tenant: "acme" };

test("a request carries the token and the active tenant", () => {
  expect(sessionHeaders(session)).toEqual({ Authorization: "Bearer t0k3n", "X-Tenant": "acme" });
});

test("before a tenant is chosen, a request names none", () => {
  expect(sessionHeaders({ token: "t0k3n", tenant: null })).toEqual({
    Authorization: "Bearer t0k3n",
  });
});

test("a stream carries them in its query, on the surface's scheme", () => {
  expect(streamUrl("https://app.example/artifactr/v1/", "ws 1", session)).toBe(
    "wss://app.example/artifactr/v1/workspaces/ws%201/stream?access_token=t0k3n&tenant=acme",
  );
  expect(streamUrl("http://localhost:8000/v1", "ws_1", session)).toMatch(
    /^ws:\/\/localhost:8000\//,
  );
});
