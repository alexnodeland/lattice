/**
 * A dashboard an agent wrote, as data (lattice RFC-0005): a snapshot of figures and when they were
 * true, its panels read from the data and laid out, each drawn by its type's renderer
 * (`dashboard-panels.tsx`). A chart holds `MAX_SERIES` series, which the package holds a panel
 * to; a table, 500 rows at most. What doesn't fit is left out and counted, never thrown on.
 */

import { type ComponentType, useRef } from "react";
import type { Dashboard, DonutPart, Keyed, Panel, Row, TableRow } from "./artifactr-ui";
import { formatNumber, MAX_SERIES } from "./chart-theme";
import { useChartTokens } from "./chart-tokens";
import { type FormOf, PANELS, type PanelProps, type PanelRenderers } from "./dashboard-panels";
import { isNumber, isObject, isString } from "./json";
import { realMoment } from "./moment";
import { TYPE } from "./type";

const keyed = (value: unknown): value is Keyed =>
  isObject(value) && isString(value.key) && isString(value.name);

const isRow = (value: unknown): value is Row =>
  isObject(value) &&
  Object.values(value).every((cell) => cell === null || isString(cell) || isNumber(cell));

const isTableRow = (value: unknown): value is TableRow =>
  isObject(value) &&
  Object.values(value).every(
    (cell) => cell === null || isString(cell) || isNumber(cell) || typeof cell === "boolean",
  );

const isPart = (value: unknown): value is DonutPart =>
  isObject(value) && isString(value.key) && isString(value.name) && isNumber(value.value);

const every = <T,>(value: unknown, is: (one: unknown) => one is T): value is readonly T[] =>
  Array.isArray(value) && value.every(is);

/** Whether a panel is one this view can show, whole: a type it knows, with the fields it needs. */
function readable(panel: unknown): panel is Panel {
  if (!isObject(panel)) {
    return false;
  }
  switch (panel.type) {
    case "stat":
      return (
        isString(panel.label) &&
        (isNumber(panel.value) || isString(panel.value)) &&
        (panel.unit == null || isString(panel.unit)) &&
        (panel.change == null || isNumber(panel.change))
      );
    case "bar":
    case "line":
      return (
        isString(panel.label) &&
        keyed(panel.index) &&
        every(panel.series, keyed) &&
        panel.series.length >= 1 &&
        panel.series.length <= MAX_SERIES &&
        every(panel.rows, isRow)
      );
    case "donut":
      return isString(panel.label) && every(panel.parts, isPart) && panel.parts.length > 0;
    case "table":
      return (
        isString(panel.label) &&
        every(panel.columns, keyed) &&
        panel.columns.length > 0 &&
        every(panel.rows, isTableRow)
      );
    case "text":
      return isString(panel.text);
    case "form":
      return isString(panel.form_id);
    default:
      return false;
  }
}

/**
 * A dashboard artifact's data, as a dashboard to show, or null where they aren't one. A panel
 * this can't show is left out, and counted, so the view can say so.
 */
export function readDashboard(
  data: unknown,
): { readonly dashboard: Dashboard; readonly unshown: number } | null {
  if (!(isObject(data) && Array.isArray(data.panels))) {
    return null;
  }
  const panels = data.panels.filter(readable);
  return {
    dashboard: {
      title: isString(data.title) ? data.title : "",
      panels,
      as_of: isString(data.as_of) ? data.as_of : "",
    },
    unshown: data.panels.length - panels.length,
  };
}

const MOMENT = new Intl.DateTimeFormat("en-GB", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "UTC",
});

/**
 * When the figures were true, in UTC, as the charts' days are; as it came, where it isn't a moment
 * as RFC 3339 writes one.
 */
function AsOf({ at }: { at: string }) {
  return (
    <p className={TYPE.meta}>
      Figures as of{" "}
      {realMoment(at) ? (
        <time dateTime={at}>{MOMENT.format(new Date(at.toUpperCase()))} UTC</time>
      ) : (
        at
      )}
    </p>
  );
}

/** Where a form can't be read: said, with its id. */
const NO_FORM: FormOf = (id) => (
  <p className={TYPE.meta}>
    A form, <code className="font-mono">{id}</code>, which can't be shown here.
  </p>
);

/**
 * A dashboard's panels, in their order: figures that come together side by side, as many to a row
 * as fit, and every other panel on a card of its own, the width of the view. When the figures were
 * true is said first. Each panel is drawn by `panels`' renderer for its type; a form panel's form is
 * `form`'s to read and show.
 */
export function DashboardView({
  dashboard,
  unshown = 0,
  form = NO_FORM,
  panels = PANELS,
}: {
  dashboard: Dashboard;
  /** How many panels couldn't be shown, which it says. */
  unshown?: number;
  form?: FormOf;
  /** What draws each type of panel: the kit's, unless an application gives its own. */
  panels?: PanelRenderers;
}) {
  const view = useRef<HTMLDivElement>(null);
  // The kit's renderers draw with the tokens themselves; another's may compute with them.
  const tokens = useChartTokens(view, panels !== PANELS);
  // Figures that come together are one row; every other panel is a row of its own. A snapshot's
  // panels never move, so each is keyed by its place.
  type Placed = { readonly key: string; readonly panel: Panel };
  const rows: ({ key: string; stats: Placed[] } | Placed)[] = [];
  for (const [at, panel] of dashboard.panels.entries()) {
    const key = `panel-${at}`;
    const last = rows.at(-1);
    if (panel.type !== "stat") {
      rows.push({ key, panel });
    } else if (last && "stats" in last) {
      last.stats.push({ key, panel });
    } else {
      rows.push({ key, stats: [{ key, panel }] });
    }
  }
  const drawn = ({ key, panel }: Placed) => {
    // The registry's renderer for this panel's type takes this very panel, which the compiler
    // can't follow through the lookup.
    const Draw = panels[panel.type] as ComponentType<PanelProps<Panel>>;
    return <Draw key={key} panel={panel} form={form} tokens={tokens} />;
  };
  return (
    <div ref={view} className="flex flex-col gap-4">
      {dashboard.as_of && <AsOf at={dashboard.as_of} />}
      {rows.map((row) =>
        "stats" in row ? (
          <div key={row.key} className="grid grid-cols-[repeat(auto-fit,minmax(9rem,1fr))] gap-3">
            {row.stats.map(drawn)}
          </div>
        ) : (
          drawn(row)
        ),
      )}
      {unshown > 0 && (
        <p className={TYPE.note}>
          {unshown === 1
            ? "One panel can't be shown here."
            : `${formatNumber(unshown)} panels can't be shown here.`}
        </p>
      )}
    </div>
  );
}
