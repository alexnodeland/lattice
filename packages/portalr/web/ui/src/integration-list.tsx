import { type ReactNode, useId } from "react";
import { Button } from "./button";
import { ItemTable } from "./item-table";
import { Moment } from "./moment";
import { StatusBadge } from "./status-badge";
import { Switch } from "./switch";

/**
 * Where an integration's state at a level comes from: its default, the tenant's setting, a setting
 * at this level, or a ceiling no setting here lifts, the tenant's off or the deployment's not
 * installing it (grantr ADR-0034).
 */
export type Source = "default" | "inherited" | "set" | "tenant-off" | "not-installed";

/** One integration at a level, as the list shows it. */
export interface IntegrationRow {
  readonly key: string;
  /** What people call it, such as "Mermaid". */
  readonly name: string;
  /** What it is, in a sentence. */
  readonly description: string;
  /** Whether it is on at this level. */
  readonly on: boolean;
  readonly source: Source;
  /** Who set it at this level, as people read them, and when; null where this level hasn't. */
  readonly changed: { readonly by: string; readonly at: string } | null;
}

const SOURCE: Record<Source, string> = {
  default: "Default",
  inherited: "Inherited from the tenant",
  set: "Set here",
  "tenant-off": "Off for the tenant",
  "not-installed": "Not installed in this deployment",
};

/** Why a switch can't be turned here, where it can't: a ceiling above it. */
const CEILING: Partial<Record<Source, string>> = {
  "tenant-off": "The tenant turned it off, so no workspace can turn it on.",
  "not-installed": "This deployment doesn't install it, so it is off everywhere.",
};

/**
 * A level's integrations, in the registry's order: each one's name, key and sentence; a switch,
 * named by the integration and described by its state in words, beside a badge whose shape says
 * on or off, so no state is told by colour alone; where the state comes from; who set it here,
 * and when; and, where this level has a setting of its own, a way back to what it inherits. A
 * switch under a ceiling is disabled, with the reason beside it, and one saving is disabled
 * until it is answered (portalr ADR-0045).
 */
export function IntegrationList({
  caption,
  level,
  rows,
  saving,
  onSwitch,
  onInherit,
  history,
}: {
  caption: string;
  /** The level shown: on the tenant, unsetting goes back to the default. */
  level: "tenant" | "workspace";
  rows: readonly IntegrationRow[];
  /** The keys of the integrations whose change is in flight. */
  saving: ReadonlySet<string>;
  onSwitch: (key: string, on: boolean) => void;
  onInherit: (key: string) => void;
  /** A way to the record of an integration's changes, such as the audit log, filtered. */
  history?: ((row: IntegrationRow) => ReactNode) | undefined;
}) {
  const back = level === "tenant" ? "Back to the default" : "Back to inherited";
  return (
    <ItemTable
      caption={caption}
      columns={[
        {
          key: "integration",
          label: "Integration",
          width: "40%",
          cell: (row) => (
            <span className="flex flex-col gap-0.5 whitespace-normal font-normal">
              <span className="font-semibold">{row.name}</span>
              <code className="font-mono text-muted text-xs">{row.key}</code>
              <span className="text-muted text-sm">{row.description}</span>
            </span>
          ),
        },
        {
          key: "state",
          label: "State",
          width: "30%",
          cell: (row) => <State row={row} saving={saving.has(row.key)} onSwitch={onSwitch} />,
        },
        {
          key: "changed",
          label: "Changed here",
          cell: (row) => (
            <span className="flex flex-col gap-0.5 text-sm">
              {row.changed ? (
                <>
                  <span>{row.changed.by}</span>
                  <span className="text-muted text-xs">
                    <Moment at={row.changed.at} />
                  </span>
                </>
              ) : (
                <span className="text-muted">Not set here</span>
              )}
              {history?.(row)}
            </span>
          ),
        },
      ]}
      items={rows}
      keyOf={(row) => row.key}
      named={(row) => row.name}
      actions={(row) =>
        row.changed && (
          <Button
            variant="ghost"
            size="sm"
            disabled={saving.has(row.key)}
            onClick={() => onInherit(row.key)}
          >
            {back}
            <span className="sr-only"> for {row.name}</span>
          </Button>
        )
      }
      empty={{ title: "No integrations", body: "This deployment declares none." }}
    />
  );
}

/** An integration's switch, and its state in words, which describe it. */
function State({
  row,
  saving,
  onSwitch,
}: {
  row: IntegrationRow;
  saving: boolean;
  onSwitch: (key: string, on: boolean) => void;
}) {
  const said = useId();
  const ceiling = CEILING[row.source];
  return (
    <span className="flex items-start gap-3">
      <Switch
        aria-label={row.name}
        aria-describedby={said}
        checked={row.on}
        disabled={saving || ceiling !== undefined}
        onCheckedChange={(on) => onSwitch(row.key, on)}
        className="mt-0.5 shrink-0"
      />
      <span id={said} className="flex flex-col items-start gap-1">
        <StatusBadge tone={saving ? "working" : row.on ? "done" : "stopped"}>
          {saving ? "Saving…" : row.on ? "On" : "Off"}
        </StatusBadge>
        <span className="text-xs">{SOURCE[row.source]}</span>
        {ceiling && <span className="text-muted text-xs">{ceiling}</span>}
      </span>
    </span>
  );
}
