/**
 * Commands sent over a library's REST rather than its stream, for an answer to every one.
 *
 * A stream answers a command it can't read with an error frame that names no command, so a
 * command typed by hand, such as a rule's JSON, would never settle there. Its REST route answers
 * each request: carried out, refused with the library's rejection, or refused by FastAPI's
 * validation when the body isn't a command at all (portalr ADR-0020).
 */

import type { components as Grantr } from "./generated/grantr.openapi";
import type { components as Portalr } from "./generated/portalr.openapi";
import type { components } from "./generated/reflexr.openapi";
import { reasons } from "./reasons";
import { type Api, named } from "./rest";

type Command = components["schemas"]["Command"];
type Result = components["schemas"]["CommandResult"];
type GrantRequest = Grantr["schemas"]["GrantRequest"];
type Restriction = Grantr["schemas"]["Restriction"];
type AuditEntry = Grantr["schemas"]["AuditEntry"];
type Member = Grantr["schemas"]["Member"];
type IssuedKey = Grantr["schemas"]["IssuedKey"];
type Invited = Portalr["schemas"]["Invited"];
type CreatedTenant = Portalr["schemas"]["CreatedTenant"];

/** A command's answer: carried out, with what the server answered, or refused, with each reason. */
export type Answer<R = Result> = { readonly outcome: "done"; readonly result: R } | Refusal;

/** A command that wasn't carried out: the status it was answered with (0 for none), and why. */
export interface Refusal {
  readonly outcome: "refused";
  readonly status: number;
  readonly reasons: readonly string[];
}

/** FastAPI's account of a body it couldn't validate. */
/** What a field or a form says of a command that wasn't done, after what it would have done. */
export const refusal = (undone: string, refused: Refusal) =>
  `${undone}: ${refused.reasons.join("; ")}`;

/**
 * What a done command answered, or an error that says why it wasn't done, for a caller that
 * stays open on a throw, such as a confirming dialog.
 */
export function orThrow<R>(undone: string, answer: Answer<R>): R {
  if (answer.outcome === "refused") {
    throw new Error(refusal(undone, answer));
  }
  return answer.result;
}

/**
 * The commands the UIs send over REST, over the given clients: reflexr's, and grantr's changes to
 * who may see and do what. `unsigned` is called when one is refused because no one is signed in,
 * as a read refused so ends the session.
 */
export function createCommands(api: Api, unsigned: () => void = () => {}) {
  /**
   * A request's answer, from what openapi-fetch resolves with: `done` if the server says so of
   * the body it answered.
   */
  async function answer<D>(
    sent: Promise<{ data?: D; error?: unknown; response: Response }>,
    done: (data: D) => boolean = () => true,
  ): Promise<Answer<D>> {
    const answered = await sent.catch(() => null); // fetch throws when nothing answers
    if (answered === null) {
      return { outcome: "refused", status: 0, reasons: ["The server couldn't be reached."] };
    }
    const { data, error, response } = answered;
    if (data !== undefined && done(data)) {
      return { outcome: "done", result: data };
    }
    if (response.status === 401) {
      unsigned();
    }
    return {
      outcome: "refused",
      status: response.status,
      reasons: reasons(response.status, data ?? error),
    };
  }
  /** A grantr request in a tenant, with any more of its path: the header names it, as every read sends. */
  const inTenant = <P extends Record<string, string>>(tenant: string, path: P) => ({
    ...named(tenant),
    params: { path: { tenant, ...path } },
  });
  return {
    reflexr: {
      /** Send one command to a workspace, once: the same `id` makes a retry the same command. */
      send: (
        tenant: string,
        ws: string,
        command: Command,
        id: string = crypto.randomUUID(),
      ): Promise<Answer> =>
        answer(
          api.reflexr.POST("/workspaces/{workspace_id}/commands", {
            ...named(tenant),
            params: { path: { workspace_id: ws } },
            body: { type: "command", command_id: id, command },
          }),
          (result) => result.ok,
        ),
    },
    grantr: {
      /** Grant a role on a resource, such as a thread, to a member of the tenant. */
      grant: (tenant: string, request: GrantRequest): Promise<Answer<AuditEntry>> =>
        answer(
          api.grantr.POST("/grantr/v1/tenants/{tenant}/grants", {
            ...inTenant(tenant, {}),
            body: request,
          }),
        ),
      /** Take a grant back. */
      revoke: (tenant: string, request: GrantRequest): Promise<Answer<AuditEntry>> =>
        answer(
          api.grantr.POST("/grantr/v1/tenants/{tenant}/revocations", {
            ...inTenant(tenant, {}),
            body: request,
          }),
        ),
      /** Restrict a thread or artifact to those granted a role on it, or lift that. */
      restrict: (tenant: string, restriction: Restriction): Promise<Answer<AuditEntry>> =>
        answer(
          api.grantr.POST("/grantr/v1/tenants/{tenant}/restrictions", {
            ...inTenant(tenant, {}),
            body: restriction,
          }),
        ),
      /** Add a user or a service principal to the tenant: a service principal is made so. */
      addMember: (tenant: string, member: Member): Promise<Answer<AuditEntry>> =>
        answer(
          api.grantr.POST("/grantr/v1/tenants/{tenant}/members", {
            ...inTenant(tenant, {}),
            body: { member },
          }),
        ),
      /** Remove a member, with their grants, their places in groups, and their keys. */
      removeMember: (tenant: string, member: Member): Promise<Answer<AuditEntry>> =>
        answer(
          api.grantr.DELETE(`/grantr/v1/tenants/{tenant}/members/${member.kind}/{member_id}`, {
            ...inTenant(tenant, { member_id: member.id }),
          }),
        ),
      /** Create a group, or replace its members. */
      defineGroup: (
        tenant: string,
        group: string,
        members: readonly Member[],
      ): Promise<Answer<AuditEntry>> =>
        answer(
          api.grantr.PUT("/grantr/v1/tenants/{tenant}/groups/{group}", {
            ...inTenant(tenant, { group }),
            body: { members: [...members] },
          }),
        ),
      /** Delete a group, with its grants. */
      deleteGroup: (tenant: string, group: string): Promise<Answer<AuditEntry>> =>
        answer(
          api.grantr.DELETE("/grantr/v1/tenants/{tenant}/groups/{group}", {
            ...inTenant(tenant, { group }),
          }),
        ),
      /** Create a custom role, or replace its actions. */
      defineRole: (
        tenant: string,
        name: string,
        actions: readonly string[],
      ): Promise<Answer<AuditEntry>> =>
        answer(
          api.grantr.PUT("/grantr/v1/tenants/{tenant}/roles/{name}", {
            ...inTenant(tenant, { name }),
            body: { actions: [...actions] },
          }),
        ),
      /** Delete a custom role, with its grants. */
      deleteRole: (tenant: string, name: string): Promise<Answer<AuditEntry>> =>
        answer(
          api.grantr.DELETE("/grantr/v1/tenants/{tenant}/roles/{name}", {
            ...inTenant(tenant, { name }),
          }),
        ),
      /** Issue a key for a service principal: its secret is in the answer, and nowhere after. */
      issueKey: (tenant: string, principal: string): Promise<Answer<IssuedKey>> =>
        answer(
          api.grantr.POST("/grantr/v1/tenants/{tenant}/keys", {
            ...inTenant(tenant, {}),
            body: { principal },
          }),
        ),
      /** Revoke a key, by its public id. */
      revokeKey: (tenant: string, key: string): Promise<Answer<AuditEntry>> =>
        answer(
          api.grantr.DELETE("/grantr/v1/tenants/{tenant}/keys/{key_id}", {
            ...inTenant(tenant, { key_id: key }),
          }),
        ),
    },
    portalr: {
      /** Invite someone by email to the tenant, through Supabase Auth, and add them to it. */
      invite: (tenant: string, email: string): Promise<Answer<Invited>> =>
        answer(api.portalr.POST("/portalr/v1/invites", { ...named(tenant), body: { email } })),
      /**
       * Create a tenant, its first owner invited or found by email, for operators. The answer is
       * the tenant and the owner's user id: the email is not kept, nor answered with.
       */
      createTenant: (tenant: string, ownerEmail: string): Promise<Answer<CreatedTenant>> =>
        answer(
          api.portalr.POST("/portalr/v1/deployment/tenants", {
            body: { tenant, owner_email: ownerEmail },
          }),
        ),
    },
  };
}
