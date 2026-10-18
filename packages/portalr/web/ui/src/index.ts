/**
 * @portalr/ui: the kit app and admin build from.
 *
 * Its primitives are Base UI's, styled with portalr's tokens through Tailwind; `styles.css` holds
 * both.
 */

export { Account } from "./account";
export { AccountMenu, type Appearance } from "./account-menu";
export { type Addons, AddonsProvider } from "./addons";
export { Alert, type AlertTone } from "./alert";
export { AnsiText, type Run, runs } from "./ansi";
export { AppShell } from "./app-shell";
export { useAppearance } from "./appearance";
export {
  ArtifactContent,
  type Data,
  Diff,
  json,
  LONGEST_TITLE,
  markdown,
  plainTitle,
  type Renderer,
  type Renderers,
  rendererFor,
} from "./artifacts";
export { Button, type ButtonSize, type ButtonVariant } from "./button";
export { Card } from "./card";
export {
  BarChart,
  type Datum,
  DonutChart,
  LineChart,
  MAX_SERIES,
  type Part,
  type Series,
} from "./chart";
export { formatDay, formatMoment, formatNumber } from "./chart-theme";
export {
  CommandButton,
  Composer,
  type GiveThumbs,
  Message,
  Messages,
  ProposalCard,
  proposedOn,
  Request,
  RunStatus,
  type Sent,
  Streaming,
  Thumbs,
  ToolCall,
} from "./chat";
export { type CheckboxChoice, CheckboxGroup } from "./checkbox";
export { useColourBlind } from "./colour-blind";
export { ConfirmDialog } from "./confirm-dialog";
export { Dialog } from "./dialog";
export { EmptyState } from "./empty-state";
export { failureSaid } from "./failure";
export { Icon } from "./icon";
export { IntegrationList, type IntegrationRow, type IntegrationSource } from "./integration-list";
export { type Column, ItemTable } from "./item-table";
export { type LineReveal, LogList } from "./log-list";
export { Markdown } from "./markdown";
export { Lockup, Mark, type Ui } from "./marks";
export { Menu, type MenuItem } from "./menu";
export { ago, Moment } from "./moment";
export { Num } from "./num";
export { PageHeader } from "./page-header";
export { Plain } from "./plain";
export { Row, RowLink, Rows } from "./rows";
export { RuleRunStatus, RunList, type RunParts } from "./run-list";
export { safeHref } from "./safe-href";
export { SectionTitle } from "./section-title";
export { type Segment, SegmentedFilter } from "./segmented-filter";
export { type Option, SelectField } from "./select-field";
export { NavLink, SideNav } from "./side-nav";
export { SignIn } from "./sign-in";
export { Reading, Skeleton } from "./skeleton";
export { StatCard } from "./stat-card";
export { StatusBadge, type Tone } from "./status-badge";
export { Switch } from "./switch";
export { type Choice, Switcher, TenantSwitcher } from "./switcher";
export { TabLink, TabNav } from "./tab-nav";
export { Table } from "./table";
export { TextField } from "./text-field";
export { TextLink } from "./text-link";
export { duration, type Reveal, type Standing, TraceView } from "./trace-view";
export { type Block, type Level, Tracker } from "./tracker";
export { type TrackerItem, TrackerItems, trackerName } from "./tracker-items";
