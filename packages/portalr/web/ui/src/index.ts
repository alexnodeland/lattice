/**
 * @portalr/ui: the kit app and admin build from.
 *
 * Its primitives are Base UI's, styled with portalr's tokens through Tailwind; `styles.css` holds
 * both.
 */

export { AccountMenu, type Appearance } from "./account-menu";
export { AppShell } from "./app-shell";
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
  Composer,
  Message,
  Messages,
  ProposalCard,
  proposedOn,
  Request,
  RunStatus,
  type Sent,
  Streaming,
  ToolCall,
} from "./chat";
export { EmptyState } from "./empty-state";
export { Icon } from "./icon";
export { Markdown } from "./markdown";
export { Lockup, Mark, type Ui } from "./marks";
export { Page } from "./page";
export { PageHeader } from "./page-header";
export { type Segment, SegmentedFilter } from "./segmented-filter";
export { NavLink, SideNav } from "./side-nav";
export { StatusBadge, type Tone } from "./status-badge";
export { Switch } from "./switch";
export { type Choice, Switcher } from "./switcher";
export { Table } from "./table";
export { TextField } from "./text-field";
export { TextLink } from "./text-link";
