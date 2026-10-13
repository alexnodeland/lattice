/**
 * @portalr/ui: the kit app and admin build from.
 *
 * Its primitives are Base UI's, styled with portalr's tokens through Tailwind; `styles.css` holds
 * both.
 */

export { Account } from "./account";
export { AccountMenu, type Appearance } from "./account-menu";
export { AppShell } from "./app-shell";
export { useAppearance } from "./appearance";
export {
  ArtifactContent,
  type Data,
  Diff,
  json,
  markdown,
  type Renderer,
  type Renderers,
  rendererFor,
} from "./artifacts";
export { Button } from "./button";
export { Card } from "./card";
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
export { ConfirmDialog } from "./confirm-dialog";
export { Dialog } from "./dialog";
export { EmptyState } from "./empty-state";
export { Icon } from "./icon";
export { Markdown } from "./markdown";
export { Lockup, Mark, type Ui } from "./marks";
export { Menu, type MenuItem } from "./menu";
export { PageHeader } from "./page-header";
export { Plain } from "./plain";
export { Row, RowLink, Rows } from "./rows";
export { SectionTitle } from "./section-title";
export { type Segment, SegmentedFilter } from "./segmented-filter";
export { SelectField } from "./select-field";
export { NavLink, SideNav } from "./side-nav";
export { SignIn } from "./sign-in";
export { StatCard } from "./stat-card";
export { StatusBadge, type Tone } from "./status-badge";
export { Switch } from "./switch";
export { type Choice, Switcher, TenantSwitcher } from "./switcher";
export { Table } from "./table";
export { TextField } from "./text-field";
export { TextLink } from "./text-link";
