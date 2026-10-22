/**
 * @portalr/client: the only code in portalr's UIs that talks to the server.
 *
 * Its types are generated from each package's committed documents (`src/generated/`). It holds
 * the REST clients, the queries' keys and options, and a store per workspace stream, with a
 * reducer for each protocol.
 */

export { changedAccess } from "./access";
export { allowedIn, workspaceOf } from "./allowed";
export type * as Artifactr from "./artifactr";
export { type ArtifactrStream, artifactr } from "./artifactr";
export { type Answer, createCommands, orThrow, type Refusal, refusal } from "./commands";
export { type Change, changes, type Granularity } from "./diff";
export { type Feedback, type Thumb, thumbs } from "./feedback";
export {
  type CheckedIn,
  checkIn,
  newArtifactId,
  type Quota,
  type UploadAnswer,
  type Uploaded,
  type Uploads,
  uploadFile,
} from "./files";
export type * as ArtifactrApi from "./generated/artifactr.openapi";
export type * as ArtifactrV1 from "./generated/artifactr.v1";
export type * as ArtifactrExcalidrawV1 from "./generated/artifactr_excalidraw.v1";
export type * as ArtifactrUiV1 from "./generated/artifactr_ui.v1";
export type * as FilesApi from "./generated/files.openapi";
export type * as GrantrApi from "./generated/grantr.openapi";
export { INTEGRATIONS } from "./generated/integrations";
export type * as PortalrApi from "./generated/portalr.openapi";
export type * as ReflexrApi from "./generated/reflexr.openapi";
export type * as ReflexrRulesV1 from "./generated/reflexr.rules.v1";
export type * as ReflexrV1 from "./generated/reflexr.v1";
export type * as RelayrApi from "./generated/relayr.openapi";
export { changedIntegrations, type IntegrationKey, useEnabled } from "./integrations";
export {
  type AdminLanding,
  administered,
  adminLanding,
  type Landing,
  landing,
} from "./landing";
export type { LogRecord, Logs } from "./logs";
export { useMe } from "./me";
export { keepWithin, type Names, namesOf, shortId, usePeople } from "./people";
export {
  type AuditFilter,
  createQueries,
  type Filed,
  type FiledItem,
  type Following,
  keys,
  LOGS_LIMIT,
  type LogFilter,
  Refused,
  stale,
  type TimeSpan,
  type ToolIds,
  TRACES_LIMIT,
  type TraceFilter,
} from "./queries";
export { createQueryClient } from "./query-client";
export type * as Reflexr from "./reflexr";
export { type ReflexrStream, RUN_EVENTS, reflexr } from "./reflexr";
export { type Api, type Config, createApi, readConfig, type Surfaces } from "./rest";
export { type Session, type StreamSession, sessionHeaders, streamUrl } from "./session";
export { authUrl, type SessionChange, Signed } from "./signed";
export {
  type Classified,
  type Envelope,
  type Protocol,
  type Result,
  type Settled,
  type Snapshot,
  type Status,
  Stream,
  type StreamOptions,
} from "./stream";
export {
  type Kind,
  type Outline,
  outline,
  type Row,
  type Said,
  said,
  type Trace,
  wholeTrace,
} from "./traces";
export { filedBy, type TrackerItem } from "./trackers";
