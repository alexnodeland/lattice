import { expect, test, vi } from "vitest";
import { Refused } from "./queries";
import { createQueryClient } from "./query-client";

const refused = (status: number) => async () => {
  throw new Refused(status, null);
};

test("a read refused for no one signed in ends the session, and isn't asked again", async () => {
  const unsigned = vi.fn();
  const client = createQueryClient(unsigned);
  const read = vi.fn(refused(401));
  await expect(client.fetchQuery({ queryKey: ["one"], queryFn: read })).rejects.toThrow(Refused);
  expect(read).toHaveBeenCalledOnce();
  expect(unsigned).toHaveBeenCalledOnce();
});

test("a read refused for what was asked isn't asked again; one that failed otherwise is", async () => {
  const unsigned = vi.fn();
  const client = createQueryClient(unsigned);
  const forbidden = vi.fn(refused(403));
  await expect(client.fetchQuery({ queryKey: ["two"], queryFn: forbidden })).rejects.toThrow();
  expect(forbidden).toHaveBeenCalledOnce();
  expect(client.getDefaultOptions().queries?.retry).toBeInstanceOf(Function);
  const retry = client.getDefaultOptions().queries?.retry as (n: number, e: unknown) => boolean;
  expect(retry(0, new Error("down"))).toBe(true);
  expect(retry(3, new Error("down"))).toBe(false);
  expect(unsigned).not.toHaveBeenCalled();
});
