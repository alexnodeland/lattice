/**
 * @portalr/ui: the kit app and admin build from.
 *
 * Its primitives are Base UI's, styled with portalr's tokens through Tailwind; `styles.css` holds
 * both.
 */

export { Account } from "./account";
export { AccountMenu, type Appearance } from "./account-menu";
export { Alert, type AlertTone } from "./alert";
export { AnsiText, type Run, runs } from "./ansi";
export { type AppHost, AppHostContext } from "./app-frame";
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
  type RevisionPart,
  rendererFor,
} from "./artifacts";
export { Badge } from "./badge";
export { type Brand, BrandContext, brandName, pageTitle, useBrand, useUiName } from "./brand";
export { Breadcrumbs, type Crumb } from "./breadcrumbs";
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
export type { ChartTokens } from "./chart-tokens";
export {
  ASK_FORM,
  ASK_USER,
  CommandButton,
  Composer,
  type GiveThumbs,
  InlineArtifact,
  Message,
  Messages,
  ProposalCard,
  proposedOn,
  Request,
  RunStatus,
  Streaming,
  Thumbs,
} from "./chat";
export { Checkbox, type CheckboxChoice, CheckboxGroup } from "./checkbox";
export { useColourBlind } from "./colour-blind";
export { ComposerDock } from "./composer-dock";
export { ConfirmDialog } from "./confirm-dialog";
export { type FormOf, PANELS, type PanelProps, type PanelRenderers } from "./dashboard-panels";
export { DashboardView } from "./dashboard-view";
export { Dialog } from "./dialog";
export { Disclosure } from "./disclosure";
export { EmptyState } from "./empty-state";
export { ErrorState } from "./error-state";
export { failureSaid } from "./failure";
export { FileChooser } from "./file-chooser";
export { PageViewer, SheetTable, sheetsOf } from "./file-preview";
export { Heading } from "./heading";
export { Icon } from "./icon";
export { IconButton } from "./icon-button";
export { IntegrationList, type IntegrationRow, type IntegrationSource } from "./integration-list";
export { IntegrationsContext, type IsEnabled } from "./integrations";
export { type Column, ItemTable } from "./item-table";
export { type LineReveal, LogList } from "./log-list";
export { Markdown } from "./markdown";
export { Lockup, Mark, type Ui } from "./marks";
export { Menu, type MenuItem } from "./menu";
export { Ago, ago, Moment } from "./moment";
export {
  FileHolder,
  factsOf,
  fileSize,
  type Holder,
  nativeFile,
  PageCompare,
  type PagePair,
  type PageShown,
  PageStrip,
} from "./native-file";
export { NewVersion, NewVersionOffer } from "./new-version";
export { Num } from "./num";
export { PageHeader } from "./page-header";
export { Plain } from "./plain";
export { Progress } from "./progress";
export { Questions, type QuestionsAnswer } from "./questions";
export { type Compare, type More, type RevisionShown, Revisions } from "./revisions";
export { Row, RowLink, Rows } from "./rows";
export { RunFailed } from "./run-failed";
export { RuleRunStatus, RunList, type RunParts } from "./run-list";
export { safeHref } from "./safe-href";
export { SchemaForm } from "./schema-form";
export { ScrollRegion } from "./scroll-region";
export { SectionTitle } from "./section-title";
export { type Segment, SegmentedFilter } from "./segmented-filter";
export { type Option, SelectField } from "./select-field";
export type { Sent } from "./sending";
export { NavLink, SideNav } from "./side-nav";
export { SignIn } from "./sign-in";
export { Reading, Skeleton } from "./skeleton";
export { StatCard } from "./stat-card";
export { StatusBadge, type Tone } from "./status-badge";
export { principalOf } from "./submission-id";
export { Switch } from "./switch";
export { type Choice, Switcher, TenantSwitcher } from "./switcher";
export { TabLink, TabNav } from "./tab-nav";
export { Table } from "./table";
export { TextArea } from "./text-area";
export { TextField } from "./text-field";
export { type LinkVariant, TextLink } from "./text-link";
export { ToolCall, ToolCalls } from "./tool-call";
export { duration, type Reveal, type Standing, TraceView } from "./trace-view";
export { type Block, type Level, Tracker } from "./tracker";
export { type TrackerItem, TrackerItems, trackerName } from "./tracker-items";
export { type FormHost, FormHostContext, UI_RENDERERS } from "./ui-renderers";
export { plainName, type UploadItem, UploadList } from "./upload-list";
