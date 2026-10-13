import { QueryClient } from "@tanstack/react-query";
import { expect, test } from "vitest";
import { changedAccess } from "./access";
import { keys } from "./queries";

test("a change of access makes the tenant's grantr reads stale, and not another's", async () => {
  const client = new QueryClient();
  client.setQueryData(keys.grantr.members("acme"), []);
  client.setQueryData(keys.grantr.members("globex"), []);
  client.setQueryData(keys.grantr.memberships("alice"), []);
  expect(await changedAccess(client, "acme", Promise.resolve("done"))).toBe("done");
  expect(client.getQueryState(keys.grantr.members("acme"))?.isInvalidated).toBe(true);
  expect(client.getQueryState(keys.grantr.members("globex"))?.isInvalidated).toBe(false);
  expect(client.getQueryState(keys.grantr.memberships("alice"))?.isInvalidated).toBe(false);
});
