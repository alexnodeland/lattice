import { expect, test } from "vitest";
import { sessionHeaders } from "./index";

test("a request carries the token and the active tenant", () => {
  expect(sessionHeaders({ token: "t0k3n", tenant: "acme" })).toEqual({
    Authorization: "Bearer t0k3n",
    "X-Tenant": "acme",
  });
});
