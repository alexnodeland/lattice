import type { PortalrApi, TimeSpan } from "@portalr/client";
import { BarChart, EmptyState, LineChart, SectionTitle, SelectField } from "@portalr/ui";
import type { ReactNode } from "react";
import { figure } from "./format";
import { HEALTH_RANGES, type HealthHours, pointAt, stepSaid } from "./logs";

type Points = PortalrApi.components["schemas"]["Ok_list_Point__"];
export type Reading =
  | Points
  | PortalrApi.components["schemas"]["Unavailable"]
  | PortalrApi.components["schemas"]["Unconfigured"];

const TIME = { key: "time", name: "Time" } as const;

type Point = Points["data"][number];

/** A chart's read: the chart, if there are points to draw; else why there is none. */
function Drawn({
  reading,
  none,
  chart,
}: {
  reading: Reading;
  none: { title: string; body: string };
  chart: (points: readonly Point[]) => ReactNode;
}) {
  switch (reading.status) {
    case "unconfigured":
      return (
        <EmptyState title="Prometheus isn't configured">
          Latency and failed turns are read from Prometheus, which this deployment runs without.
        </EmptyState>
      );
    case "unavailable":
      return (
        <EmptyState title="Prometheus isn't answering">
          <p role="alert">{reading.reason}</p>
        </EmptyState>
      );
    case "ok":
      return reading.data.length === 0 ? (
        <EmptyState title={none.title}>{none.body}</EmptyState>
      ) : (
        chart(reading.data)
      );
  }
}

/**
 * The tenant's health, as portalr reads it from Prometheus: how long a turn takes at the 95th
 * percentile, and how many turns failed, in each step of the window, whose length is said. A
 * point with no turns in it is a gap, not a zero.
 */
export function Health({
  window,
  hours,
  latency,
  failures,
  onWindow,
}: {
  window: TimeSpan;
  hours: HealthHours;
  latency: Reading;
  failures: Reading;
  onWindow: (hours: string) => void;
}) {
  const step = window.step ?? 0;
  return (
    <section aria-labelledby="health" className="flex flex-col gap-4">
      <SectionTitle id="health">Health</SectionTitle>
      <div className="sm:max-w-xs">
        <SelectField
          label="Health window"
          value={String(hours)}
          onChange={(event) => onWindow(event.target.value)}
          options={HEALTH_RANGES.map((range) => ({
            value: String(range.hours),
            label: range.label,
          }))}
        />
      </div>
      <p className="text-muted text-sm">Each point is {stepSaid(step)}.</p>
      <Drawn
        reading={latency}
        none={{
          title: "No turns in this window",
          body: "How long a turn takes is drawn from the turns the agent has taken.",
        }}
        chart={(points) => (
          <LineChart
            label="How long a turn takes, at the 95th percentile"
            index={TIME}
            series={[{ key: "p95", name: "95th percentile" }]}
            data={points.map((point) => ({ time: pointAt(point.time, hours), p95: point.value }))}
            format={(value) => `${value.toFixed(2)} s`}
          />
        )}
      />
      <Drawn
        reading={failures}
        none={{
          title: "No failed turns in this window",
          body: "Failed turns are counted from the turns the agent has taken.",
        }}
        chart={(points) => (
          <BarChart
            label="Failed turns in each step"
            index={TIME}
            series={[{ key: "failed", name: "Failed turns" }]}
            data={points.map((point) => ({
              time: pointAt(point.time, hours),
              failed: Math.round(point.value),
            }))}
            format={(value) => figure(Math.round(value))}
          />
        )}
      />
    </section>
  );
}
