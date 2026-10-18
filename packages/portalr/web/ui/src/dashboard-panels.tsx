/**
 * What draws a dashboard's panels: a registry of renderers keyed by a panel's `type`, so how a
 * chart or a table is drawn can change without a change to the panels' format, which stays plain
 * JSON with nothing in it that runs (portalr ADR-0047). `PANELS` is the kit's: figures as
 * `StatCard`s; the charts and a table's sorting, filtering and pages from the dashboards add-on,
 * loaded on demand while `ui:dashboards` is on, each chart with its figures from the panel; text
 * as `Markdown`; and a form as its caller shows it.
 */

import { ArrowDownRight, ArrowRight, ArrowUpRight } from "lucide-react";
import { type ComponentType, type ReactNode, useId, useMemo } from "react";
import type { Panel, StatPanel, TablePanel } from "./artifactr-ui";
import { MAX_TABLE_ROWS } from "./artifactr-ui";
import { Card } from "./card";
import { formatNumber } from "./chart-theme";
import type { ChartTokens } from "./chart-tokens";
import { Figures, PlainTable } from "./dashboard-figures";
import { Icon } from "./icon";
import { DASHBOARDS, offSaid, useOff } from "./integrations";
import { isNumber } from "./json";
import { Markdown } from "./markdown";
import { useLoaded } from "./on-demand";
import { Skeleton } from "./skeleton";
import { StatCard } from "./stat-card";
import { TYPE } from "./type";

/** A form artifact a panel names, read and shown by the caller. */
export type FormOf = (id: string) => ReactNode;

/**
 * What a panel's renderer is given: the panel; how to show a form a panel names; and the chart
 * theme's colours, resolved, for a renderer that computes with them, as a canvas does. They are
 * null for the kit's own renderers, which don't, and for a first render, before they are read.
 */
export interface PanelProps<P extends Panel> {
  readonly panel: P;
  readonly form: FormOf;
  readonly tokens: ChartTokens | null;
}

/** A renderer for each type of panel, each given panels of its type alone. */
export type PanelRenderers = {
  readonly [T in Panel["type"]]: ComponentType<PanelProps<Extract<Panel, { type: T }>>>;
};

/** A figure in its unit: a number grouped, and a percent sign or a unit's word after it. */
function figureOf({ value, unit }: StatPanel): string {
  const figure = isNumber(value) ? formatNumber(value) : value;
  if (!unit) {
    return figure;
  }
  return unit === "%" ? `${figure}%` : `${figure} ${unit}`;
}

/** How a figure moved, in words beside a shape: never by colour, since up isn't always good. */
function Change({ change, unit }: { change: number; unit: string | null | undefined }) {
  const by = `${formatNumber(Math.abs(change))}${unit === "%" ? " points" : unit ? ` ${unit}` : ""}`;
  const [icon, words] =
    change > 0
      ? [ArrowUpRight, `Up ${by}`]
      : change < 0
        ? [ArrowDownRight, `Down ${by}`]
        : [ArrowRight, "No change"];
  return (
    <span className="inline-flex items-center gap-1">
      <Icon icon={icon} className="size-3.5" />
      {words}
    </span>
  );
}

/**
 * A panel that is a heading and what it holds, on a card: a chart and a table are each headed
 * alike, so a reader moving by headings finds both.
 */
function Titled({ title, children }: { title: string; children: (heading: string) => ReactNode }) {
  const heading = useId();
  return (
    <Card render={<section aria-labelledby={heading} />} className="flex flex-col gap-3">
      <h2 id={heading} className={TYPE.label}>
        {title}
      </h2>
      {children(heading)}
    </Card>
  );
}

/** The dashboards add-on: the charts, and a table's sorting, filtering and pages. */
const loadDashboards = () => import("./on-demand/dashboards");

/**
 * The dashboards add-on once it has loaded, or null; and why it won't be, if it won't: the
 * integration that is off, or that it failed to load, each of which leaves the panel's figures.
 */
function useDashboards() {
  const off = useOff([DASHBOARDS]);
  const { module, failed } = useLoaded(loadDashboards, off === null);
  const without =
    off !== null ? offSaid(off) : failed ? "The charts couldn't be loaded here." : null;
  return { addon: module, without };
}

/**
 * A table panel, under its heading: sorted, filtered and paged once the dashboards add-on has
 * loaded, and its rows as they are until then, or without it. Past `MAX_TABLE_ROWS`, the rest are
 * left out, and said so.
 */
function TableView({ panel }: PanelProps<TablePanel>) {
  const { addon } = useDashboards();
  // The same rows for as long as the panel's are, so a table's page stays as a render repeats.
  const shown = useMemo(() => ({ ...panel, rows: panel.rows.slice(0, MAX_TABLE_ROWS) }), [panel]);
  return (
    <Titled title={panel.label}>
      {(heading) => (
        <>
          {addon ? (
            <addon.DataTable panel={shown} labelledBy={heading} />
          ) : (
            <PlainTable panel={shown} labelledBy={heading} />
          )}
          {panel.rows.length > MAX_TABLE_ROWS && (
            <p className={TYPE.note}>
              The first {formatNumber(MAX_TABLE_ROWS)} rows of {formatNumber(panel.rows.length)}.
            </p>
          )}
        </>
      )}
    </Titled>
  );
}

/** A figure, on a card of its own. */
function StatView({ panel }: PanelProps<StatPanel>) {
  return (
    <StatCard title={panel.label} figure={figureOf(panel)}>
      {panel.change != null && <Change change={panel.change} unit={panel.unit} />}
    </StatCard>
  );
}

/**
 * A bar, line or donut chart, under its heading: the chart once the dashboards add-on has drawn it,
 * busy until then, and its figures from the panel. Where dashboards are off, or the add-on won't
 * load, the chart isn't drawn, one line says why, and its figures are open.
 */
function ChartView({ panel }: PanelProps<Extract<Panel, { type: "bar" | "line" | "donut" }>>) {
  const { addon, without } = useDashboards();
  return (
    <Titled title={panel.label}>
      {(heading) => (
        <figure
          aria-labelledby={heading}
          aria-busy={without === null && addon === null}
          className="m-0 flex flex-col gap-2"
        >
          {without !== null ? (
            <p className={TYPE.note}>{without} This chart isn't drawn: its figures are below.</p>
          ) : addon ? (
            <addon.Chart panel={panel} />
          ) : (
            <div className="flex flex-col gap-2 text-muted text-sm">
              Drawing the chart…
              <Skeleton className="h-4 w-2/3" />
              <Skeleton className="h-4 w-1/2" />
            </div>
          )}
          <Figures panel={panel} open={without !== null} />
        </figure>
      )}
    </Titled>
  );
}

/** Markdown, on its card, without HTML. */
function TextView({ panel }: PanelProps<Extract<Panel, { type: "text" }>>) {
  return (
    <Card>
      <Markdown>{panel.text}</Markdown>
    </Card>
  );
}

/** A form, as the caller shows it, on its card. */
function FormView({ panel, form }: PanelProps<Extract<Panel, { type: "form" }>>) {
  return <Card>{form(panel.form_id)}</Card>;
}

/** The kit's renderers, by panel type. */
export const PANELS: PanelRenderers = {
  stat: StatView,
  bar: ChartView,
  line: ChartView,
  donut: ChartView,
  table: TableView,
  text: TextView,
  form: FormView,
};
