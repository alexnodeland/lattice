/**
 * Whether a workspace has an integration switched on, asked by its key in lattice's registry,
 * such as `ui:forms` or `markdown:math`: the one seam the parts inside ask, Markdown for its
 * add-ons, and forms and dashboards for whether they may be sent and drawn. The app gives a
 * workspace's here, as grantr answers them and `client`'s `useEnabled` reads them, each its
 * registry default until they are read and where they can't be (portalr ADR-0045, ADR-0047).
 * Without a provider, as in admin, each is that default too, read from the registry's generated
 * copy. A part whose key is off degrades to read-only, as it does when the server
 * refuses a command as off.
 */

import { INTEGRATIONS, type IntegrationKey } from "@portalr/client";
import { createContext, use, useState } from "react";
import { Alert } from "./alert";

/** Whether the integration a key names is on, in the workspace shown. */
export type IsEnabled = (key: IntegrationKey) => boolean;

/** The keys that are on unless a workspace switches them off, as the registry says. */
const ON_BY_DEFAULT: ReadonlySet<IntegrationKey> = new Set(
  INTEGRATIONS.filter((known) => known.default).map((known) => known.key),
);

/** Each integration as it is where no one has set it, as the registry says. */
export const byDefault: IsEnabled = (key) => ON_BY_DEFAULT.has(key);

/** The page's answer to whether an integration is on. */
export const IntegrationsContext = createContext<IsEnabled>(byDefault);

/** The first of some integrations' keys that is off, or null if every one is on. */
export function useOff(keys: readonly IntegrationKey[]): IntegrationKey | null {
  const isEnabled = use(IntegrationsContext);
  return keys.find((key) => !isEnabled(key)) ?? null;
}

/** The keys forms and dashboards are switched by. */
const FORMS: IntegrationKey = "ui:forms";
export const DASHBOARDS: IntegrationKey = "ui:dashboards";

/**
 * The integrations a form needs on to be sent: forms, and, in a dashboard, dashboards too, which a
 * dashboard adds for the forms in it.
 */
export const FormGates = createContext<readonly IntegrationKey[]>([FORMS]);

/** What each of `ui`'s integrations is called where it is said to be off. */
const CALLED: ReadonlyMap<string, string> = new Map([
  ["ui:forms", "forms"],
  ["ui:dashboards", "dashboards"],
  ["ui:mini-apps", "mini apps"],
]);

/**
 * That an integration is off here, said of the workspace as artifactr's refusal is, never of the
 * reader's grants: and, for one of `ui`'s, which. "Not available in this workspace: forms are off."
 */
export function offSaid(integration: string): string {
  const called = CALLED.get(integration);
  return called === undefined
    ? "Not available in this workspace."
    : `Not available in this workspace: ${called} are off.`;
}

/**
 * Why a form here can't be sent for now, or null where it may be: an integration it needs that the
 * page says is off, or that the server refused it as off. A refusal holds until the page's answer
 * changes, as it does once the app reads the workspace's integrations again, and is then the
 * page's to say; `refused` records one.
 */
export function useFormLock(): { off: string | null; refused: (integration: string) => void } {
  const isEnabled = use(IntegrationsContext);
  const gated = useOff(use(FormGates));
  const [refusal, setRefusal] = useState<{ integration: string; read: IsEnabled } | null>(null);
  const off = gated ?? (refusal?.read === isEnabled ? refusal.integration : null);
  return { off, refused: (integration) => setRefusal({ integration, read: isEnabled }) };
}

/** What a form says while an integration it needs is off: it stays shown, and can't be sent. */
export function FeatureOff({ integration }: { integration: string }) {
  return <Alert tone="warn">{offSaid(integration)} This can't be sent.</Alert>;
}
