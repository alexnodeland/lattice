/**
 * What lets a page's mini apps run (lattice RFC-0005, portalr ADR-0051): the apps' origin, as
 * `config.json` names it, and the two commands an app's bridge sends as the person viewing it,
 * over the workspace's stream: its `/state` replaced, on the version it was read at, and a
 * submission to it, with its derived id. Nothing else of the workspace is an app's to reach.
 */

import type { AppHost } from "@portalr/ui";
import { useMemo } from "react";
import type { Context } from "./context";
import { useStream } from "./workspace";

/** The app host of a page in a workspace, for the deployment and the person `context` holds. */
export function useAppHost(context: Context, tenant: string, workspace: string): AppHost {
  const { config, signed } = context;
  const stream = useStream();
  return useMemo(
    () => ({
      origin: config.apps ?? null,
      place: {
        surfaces: config.surfaces,
        signed,
        tenant,
        workspace,
      },
      setState: (id, version, state) =>
        stream.send({
          type: "edit_artifact",
          artifact_id: id,
          base_version: version,
          patch: { kind: "json_patch", ops: [{ op: "replace", path: "/state", value: state }] },
        }),
      // Spread: an artifact's data is any JSON object, which an interface isn't to the compiler.
      submit: (id, submission) =>
        stream.send({
          type: "create_artifact",
          artifact_id: id,
          kind: "submission",
          data: { ...submission },
        }),
    }),
    [config, signed, tenant, workspace, stream],
  );
}
