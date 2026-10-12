/**
 * @portalr/ui: the kit app and admin build from.
 *
 * Its primitives are Base UI's, styled with portalr's tokens through Tailwind; `styles.css` holds
 * both.
 */

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
export {
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
export { Markdown } from "./markdown";
export { Page } from "./page";
export { Switch } from "./switch";
export { TextField } from "./text-field";
export { TextLink } from "./text-link";
