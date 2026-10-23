import { expect, test, vi } from "vitest";
import { Refused, refusal } from "./queries";
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

test("a read refused as busy is asked again once the server's wait has passed", async () => {
  const client = createQueryClient(vi.fn());
  const read = vi
    .fn<() => Promise<string>>()
    .mockRejectedValueOnce(new Refused(429, { detail: { type: "busy" } }, 0))
    .mockResolvedValueOnce("page");
  await expect(client.fetchQuery({ queryKey: ["busy"], queryFn: read })).resolves.toBe("page");
  expect(read).toHaveBeenCalledTimes(2);
  const delay = client.getDefaultOptions().queries?.retryDelay as (n: number, e: unknown) => number;
  const random = vi.spyOn(Math, "random").mockReturnValue(0);
  try {
    expect(delay(0, new Refused(429, null, 5))).toBe(5000);
    expect(delay(1, new Error("down"))).toBe(2000);
    expect(delay(0, new Refused(429, null, -3))).toBe(0);
    expect(delay(0, new Refused(429, null, 86_400))).toBe(300_000);
    random.mockReturnValue(0.999);
    const most = delay(0, new Refused(429, null, 5));
    expect(most).toBeGreaterThan(5990);
    expect(most).toBeLessThan(6000);
  } finally {
    random.mockRestore();
  }
});

test("a refusal carries the server's Retry-After, in seconds, or none", () => {
  const answered = (headers: Record<string, string>) =>
    new Response(null, { status: 429, headers });
  expect(refusal(answered({ "retry-after": "5" }), null).retryAfter).toBe(5);
  expect(refusal(answered({}), null).retryAfter).toBeNull();
  expect(refusal(answered({ "retry-after": "soon" }), null).retryAfter).toBeNull();
  expect(refusal(answered({}), null).status).toBe(429);
});
