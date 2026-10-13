/** Where a signed-in person lands, from the tenants grantr says they are a member of. */

/** A person in no tenant has no access; one in a single tenant goes straight to it. */
export type Landing =
  | { readonly kind: "no-access" }
  | { readonly kind: "tenant"; readonly tenant: string }
  | { readonly kind: "choose"; readonly tenants: readonly string[] };

export function landing(memberships: readonly { readonly tenant: string }[]): Landing {
  const tenants = [...new Set(memberships.map((membership) => membership.tenant))].sort();
  const [only] = tenants;
  if (only === undefined) {
    return { kind: "no-access" };
  }
  return tenants.length === 1 ? { kind: "tenant", tenant: only } : { kind: "choose", tenants };
}

/** The tenant roles that hold admin's areas: a tenant's owners' and admins'. */
const ADMINISTERS = new Set(["owner", "admin"]);

/**
 * Where admin opens for someone: a tenant they administer, every tenant if they are an
 * operator, a choice of those, or no access. Their last choice in admin, if still theirs to
 * make, comes first; the app's choice is the app's own.
 */
export type AdminLanding =
  | { readonly kind: "no-access" }
  | { readonly kind: "tenant"; readonly tenant: string }
  | { readonly kind: "deployment" }
  | { readonly kind: "choose"; readonly tenants: readonly string[]; readonly operator: boolean };

/** The tenants someone owns or administers, in order. */
export function administered(
  memberships: readonly { readonly tenant: string; readonly roles: readonly string[] }[],
): string[] {
  const tenants = memberships
    .filter((membership) => membership.roles.some((role) => ADMINISTERS.has(role)))
    .map((membership) => membership.tenant);
  return [...new Set(tenants)].sort();
}

/** `last` is admin's remembered choice: a tenant's id, `deployment`, or null for none. */
export function adminLanding(
  memberships: readonly { readonly tenant: string; readonly roles: readonly string[] }[],
  operator: boolean,
  last: string | null,
): AdminLanding {
  const tenants = administered(memberships);
  if (last === "deployment" && operator) {
    return { kind: "deployment" };
  }
  if (last !== null && tenants.includes(last)) {
    return { kind: "tenant", tenant: last };
  }
  const [only] = tenants;
  if (only === undefined) {
    return operator ? { kind: "deployment" } : { kind: "no-access" };
  }
  return tenants.length === 1 && !operator
    ? { kind: "tenant", tenant: only }
    : { kind: "choose", tenants, operator };
}
