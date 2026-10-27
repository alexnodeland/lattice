/** Where apps and editors are for the portal at an address: an alias's, the canonical, or none. */

import type { Config } from "@portalr/client";
import { expect, test } from "vitest";
import { deploymentAt, portalsOf } from "./deployment";

const LOOPBACK = "http://127.0.0.1:8800";
const TAILNET = "https://my-machine.my-tailnet.ts.net";
const EDITORS = { "files:gridcraft": "http://127.0.0.1:8802/" };
const BESIDE = {
  apps: "https://my-machine.my-tailnet.ts.net:8801",
  editors: { "files:gridcraft": "https://my-machine.my-tailnet.ts.net:8802/" },
};

const config = (given: Partial<Config>): Config => ({
  supabase: { url: "/", key: "sb_publishable_x" },
  surfaces: { artifactr: "/artifactr/v1", reflexr: "/reflexr/v1", grantr: "", portalr: "" },
  readers: {},
  people: false,
  editors: EDITORS,
  apps: "http://127.0.0.1:8801",
  aliases: {},
  replay: false,
  ...given,
});

test("without an origin named, the canonical place is trusted at any address, as before", () => {
  const trusted = { apps: "http://127.0.0.1:8801", editors: EDITORS, known: true };
  expect(deploymentAt(config({}), LOOPBACK)).toEqual(trusted);
  expect(deploymentAt(config({}), "http://localhost:8800")).toEqual(trusted);
  expect(portalsOf(config({}))).toEqual([]);
});

test("at the canonical origin the canonical place, at an alias its own, elsewhere none", () => {
  const named = config({ origin: LOOPBACK, aliases: { [TAILNET]: BESIDE } });
  expect(deploymentAt(named, LOOPBACK)).toEqual({
    apps: "http://127.0.0.1:8801",
    editors: EDITORS,
    known: true,
  });
  expect(deploymentAt(named, TAILNET)).toEqual({ ...BESIDE, known: true });
  expect(deploymentAt(named, "http://localhost:8800")).toEqual({
    apps: null,
    editors: {},
    known: false,
  });
  expect(portalsOf(named)).toEqual([LOOPBACK, TAILNET]);
});

test("an alias that runs no apps says so, and still has its editors", () => {
  const named = config({ origin: LOOPBACK, aliases: { [TAILNET]: { editors: BESIDE.editors } } });
  expect(deploymentAt(named, TAILNET)).toEqual({
    apps: null,
    editors: BESIDE.editors,
    known: true,
  });
});
