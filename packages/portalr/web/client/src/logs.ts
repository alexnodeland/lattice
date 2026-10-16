/** What portalr says of a tenant's logs (portalr ADR-0031). */

import type { components } from "./generated/portalr.openapi";

/** One log record, without its line unless it was asked for. */
export type LogRecord = components["schemas"]["LogRecord"];

/** A window's records, newest first, and whether they are all of them. */
export type Logs = components["schemas"]["Logs"];
