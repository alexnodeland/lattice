/**
 * The composer's choice of model (portalr ADR-0086, artifactr ADR-0097), loaded the first time
 * the composer takes the focus, with the models it reads: a labelled select of those the
 * workspace allows, which a message names only when it isn't the default. It starts on the model
 * last chosen in the thread, which this browser remembers, else on the default. While a turn
 * runs it is disabled and says why, as a message that joins a running turn keeps that turn's
 * model; and where the runner fell back, a quiet line says which model answered instead. None of
 * it is in the first page's bytes.
 */

import { type Api, type Artifactr, fellBack, models, type OfferedModel } from "@portalr/client";
import type { SelectField } from "@portalr/ui";
import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";

/** The model a message that names none answers with. */
export const DEFAULT = "default";

/** Where this browser remembers a thread's model. */
const key = (thread: string) => `portalr:model:${thread}`;

/** The model last chosen in a thread here, or null; storage that can't be read has none. */
export function remembered(thread: string): string | null {
  try {
    return localStorage.getItem(key(thread));
  } catch {
    return null;
  }
}

/** Remember a thread's model here; the default is remembered as nothing. */
function remember(thread: string, model: string): void {
  try {
    if (model === DEFAULT) {
      localStorage.removeItem(key(thread));
    } else {
      localStorage.setItem(key(thread), model);
    }
  } catch {
    // Without storage the choice lasts as long as the page.
  }
}

/** A model as the choices show it: its label, and that it thinks first, or runs here. */
const shown = (model: OfferedModel) =>
  [model.label, model.reasoning && "thinks first", model.local && "runs locally"]
    .filter(Boolean)
    .join(" · ");

/** Where the models are read: the workspace the thread is in. */
interface Place {
  readonly api: Api;
  readonly tenant: string;
  readonly workspace: string;
}

/** No models: one list, so that what depends on the list doesn't change while it is read. */
const NONE: readonly OfferedModel[] = [];

/** The models the workspace allows; none while they are read, or where they can't be. */
const useOffered = ({ api, tenant, workspace }: Place): readonly OfferedModel[] =>
  useQuery(models(api, tenant, workspace)).data ?? NONE;

/**
 * The model a thread starts on: the default where the workspace allows it, else the first it
 * allows, so the picker never shows nothing chosen; null is the default.
 */
const first = (offered: readonly OfferedModel[]) =>
  offered.some((model) => model.id === DEFAULT) ? null : (offered[0]?.id ?? null);

/**
 * The thread's model, chosen among those the workspace allows: nothing shown where only one is.
 * It tells the caller of the thread's remembered model once the models are read, when that is
 * still offered, else of the model it starts on, and of each choice after; null is the default.
 */
export function ModelPicker({
  place,
  thread,
  value,
  onChange,
  running,
  Select,
}: {
  place: Place;
  thread: string;
  /** The model chosen, or null for the default. */
  value: string | null;
  onChange: (model: string | null) => void;
  /** A turn is running: the next message joins it, and keeps its model. */
  running: boolean;
  /**
   * The kit's select, as the page holds it already: imported here, it would be split into a
   * chunk of its own, which every page's first load would name (portalr ADR-0086).
   */
  Select: typeof SelectField;
}) {
  const offered = useOffered(place);
  useEffect(() => {
    const last = remembered(thread);
    onChange(last !== null && offered.some((model) => model.id === last) ? last : first(offered));
  }, [thread, offered, onChange]);
  if (offered.length < 2) {
    return null;
  }
  return (
    <Select
      label="Model"
      className="w-auto flex-row items-center gap-2"
      options={offered.map((model) => ({ value: model.id, label: shown(model) }))}
      value={value ?? DEFAULT}
      onValueChange={(model) => {
        remember(thread, model);
        onChange(model === DEFAULT ? null : model);
      }}
      disabled={running}
      {...(running && { hint: "The running turn keeps its model" })}
    />
  );
}

/**
 * Says, quietly, that a turn answered with another model than its message asked for, where it
 * did: the runner's notice in the thread says why. The answer is the model the provider named,
 * once it has.
 */
export function AnsweredBy({ place, run }: { place: Place; run: Artifactr.Run }) {
  const offered = useOffered(place);
  const asked = fellBack(run);
  if (asked === null) {
    return null;
  }
  const label = offered.find((model) => model.id === asked)?.label ?? asked;
  return (
    <p className="text-muted text-xs">
      {label} wasn't used: answered by {run.live.usage?.model ?? "the default model"}
    </p>
  );
}
