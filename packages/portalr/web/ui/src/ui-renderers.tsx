/**
 * The renderers of artifactr.ui's kinds (lattice RFC-0005): a `form` that takes submissions, a
 * `submission`'s values, a `dashboard`'s panels, and an `app`, run in its sandbox where it may
 * run, through the `AppHost` its page gives, and otherwise its label and its summary. A form
 * sends through the `FormHost` its page gives, as the person viewing it, and knows which artifact
 * and version it is from `ArtifactContent`; without a host, its fields are shown as they are,
 * read-only.
 */

import { createContext, type ReactNode, use, useEffect, useRef, useState } from "react";
import { Alert } from "./alert";
import { AppFrame, type ReadApp } from "./app-frame";
import type { Form, Submission, Values } from "./artifactr-ui";
import { type Data, json, type Renderer, type Shown, ShownContext } from "./artifacts";
import type { FormOf } from "./dashboard-panels";
import { DashboardView, readDashboard } from "./dashboard-view";
import { endedBy, readForm } from "./form-schema";
import { DASHBOARDS, FeatureOff, FormGates, useFormLock } from "./integrations";
import { isObject, isString } from "./json";
import { SchemaForm } from "./schema-form";
import type { Sent } from "./sending";
import { submissionId, type Whose } from "./submission-id";
import { TYPE } from "./type";

/** What a page lets its forms do, as the person viewing it. */
export interface FormHost {
  /** The viewer's principal, as artifactr keys a person's submission: `principalOf(id)`. */
  readonly principal: string;
  /** Create a submission, with its derived id, as the viewer. */
  readonly submit: (id: string, submission: Submission) => Sent;
  /** A form artifact a dashboard's panel names, read and shown. */
  readonly form: FormOf;
}

/** The page's form host, which a page that lets its forms be sent provides. */
export const FormHostContext = createContext<FormHost | null>(null);

/** What a closed form says. */
const CLOSED = "This form is closed.";

/** What a form of each kind says once it can't be answered again. */
const ANSWERED: Record<Form["submissions"], string> = {
  once: "This form has been answered.",
  per_person: "You've answered this form.",
  many: "This form has been answered.",
};

/**
 * A form artifact, to fill in and send: its submission's id derived from the form, the viewer, or
 * a nonce kept for the submit, so a retry is the same submission. A form that changed since the
 * person opened it says so, and shows itself as it is now, with what they entered kept.
 */
function SendableForm({ form, host, shown }: { form: Form; host: FormHost; shown: Shown }) {
  const [nonce, setNonce] = useState(() => crypto.randomUUID());
  const [ended, setEnded] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  // Off in the workspace, or refused as off by the server: the form stays, and can't be sent.
  const { off, refused: refusedAsOff } = useFormLock();
  const opened = useRef(shown.version);
  useEffect(() => {
    if (opened.current !== shown.version) {
      setStale(true);
      opened.current = shown.version;
    }
  }, [shown.version]);
  const whose: Whose =
    form.submissions === "per_person"
      ? { submissions: "per_person", principal: host.principal }
      : form.submissions === "many"
        ? { submissions: "many", nonce }
        : { submissions: "once" };
  async function submit(values: Values) {
    const submission: Submission = {
      form_id: shown.id,
      version: shown.version,
      values,
      ...(whose.submissions === "many" && { nonce }),
    };
    const settled = await host.submit(await submissionId(shown.id, whose), submission);
    const refused = settled.outcome === "refused" ? endedBy(settled.result?.rejection) : null;
    if (refused?.reason === "answered" && whose.submissions === "many") {
      // Its id is this submit's own nonce's, so it is in use only if this very submission was
      // made: a retry after the first got through.
      return { outcome: "done" } as const;
    }
    if (refused?.reason === "changed") {
      setStale(true);
    } else if (refused?.reason === "off") {
      refusedAsOff(refused.integration);
    } else if (refused !== null) {
      setEnded(refused.reason === "closed" ? CLOSED : ANSWERED[form.submissions]);
    }
    return settled;
  }
  const closed = form.closed ? CLOSED : ended;
  return (
    <SchemaForm
      schema={form.schema}
      ui={form.ui}
      onSubmit={submit}
      notice={
        stale && (
          <Alert tone="warn">
            This form changed since you opened it. It's shown as it is now: check your answers.
          </Alert>
        )
      }
      {...(closed !== null && { ended: <Alert>{closed}</Alert> })}
      {...(off !== null && { locked: <FeatureOff integration={off} /> })}
      {...(form.submissions === "many" && { onAnother: () => setNonce(crypto.randomUUID()) })}
    />
  );
}

/**
 * A form artifact: sendable where the page hosts forms and says which artifact it is; else its
 * fields, shown as they are, which can't be changed or sent from here.
 */
function FormArtifact({ form }: { form: Form }) {
  const host = use(FormHostContext);
  const shown = use(ShownContext);
  return host && shown ? (
    <SendableForm form={form} host={host} shown={shown} />
  ) : (
    <SchemaForm
      schema={form.schema}
      ui={form.ui}
      onSubmit={async () => ({ outcome: "closed" })}
      locked={<Alert>This form can't be sent from here.</Alert>}
    />
  );
}

/** Data this renderer can't show, said so, with the data as JSON beneath. */
function Unreadable({ kind, data }: { kind: string; data: Data }) {
  return (
    <div className="flex flex-col gap-3">
      <Alert tone="warn">This {kind} can't be shown here. Its data are below.</Alert>
      {json.render(data)}
    </div>
  );
}

/**
 * A renderer of a kind whose data are JSON, changed line by line, titled by its `title`, and shown
 * in the thread it was made in.
 */
const ofJson = (render: (data: Data) => ReactNode): Renderer => ({ ...json, render, inline: true });

/** A `form`: its fields, to fill in and send as the viewer. */
const form = ofJson((data) => {
  const read = readForm(data);
  return read === null ? <Unreadable kind="form" data={data} /> : <FormArtifact form={read} />;
});

/** A value as a submission's list says it: a choice's words, yes or no, several joined. */
function valueText(value: unknown): string {
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  if (Array.isArray(value)) {
    return value.map(valueText).join(", ");
  }
  return typeof value === "string" || typeof value === "number"
    ? String(value)
    : JSON.stringify(value);
}

/** A `submission`: what was sent, to which form and version, each value by its field. */
const submission = ofJson((data) => {
  const values = data.values;
  if (!isObject(values)) {
    return <Unreadable kind="submission" data={data} />;
  }
  const target = [data.form_id, data.app_id].find(isString);
  return (
    <div className="flex flex-col gap-3">
      <p className={TYPE.meta}>
        {target === undefined ? (
          "Sent"
        ) : (
          <>
            Sent to <code className="font-mono">{target}</code>
          </>
        )}
        {typeof data.version === "number" && `, as it was at version ${data.version}`}.
      </p>
      {Object.keys(values).length === 0 ? (
        <p className={TYPE.meta}>Nothing was filled in.</p>
      ) : (
        <dl className="grid grid-cols-[minmax(0,auto)_1fr] gap-x-4 gap-y-2 text-sm">
          {Object.entries(values).map(([field, value]) => (
            <div key={field} className="contents">
              <dt className="text-muted">{field}</dt>
              <dd className="m-0 whitespace-pre-wrap break-words text-fg">{valueText(value)}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
});

/** The form a dashboard's panel names, as the page's host reads it, or said to be unreadable. */
function DashboardArtifact({ data }: { data: Data }) {
  const host = use(FormHostContext);
  const gates = use(FormGates);
  const read = readDashboard(data);
  if (read === null) {
    return <Unreadable kind="dashboard" data={data} />;
  }
  // A snapshot reads the same whether dashboards are on or not; its forms are sent only while
  // dashboards are on, as well as forms.
  return (
    <FormGates value={[...gates, DASHBOARDS]}>
      <DashboardView
        dashboard={read.dashboard}
        unshown={read.unshown}
        {...(host && { form: host.form })}
      />
    </FormGates>
  );
}

/** A `dashboard`: its figures as they were when it was made. */
const dashboard = ofJson((data) => <DashboardArtifact data={data} />);

/** An `app`, read: its title, summary and HTML strings, and its state an object; or null. */
function readApp(data: Data): ReadApp | null {
  const { title, summary, html, state = {} } = data;
  if (!isString(title) || !isString(summary) || !isString(html) || !isObject(state)) {
    return null;
  }
  return { title, summary, html, state: state as ReadApp["state"] };
}

/** An `app`, run in its sandbox where it may run here, its label and summary always beside it. */
function AppArtifact({ data }: { data: Data }) {
  const shown = use(ShownContext);
  const read = readApp(data);
  if (read === null) {
    return <Unreadable kind="app" data={data} />;
  }
  // Shown without knowing which artifact it is, as a preview is, it runs nothing.
  return <AppFrame app={read} shown={shown ?? { id: "", version: 0, archived: true }} />;
}

/** An `app`: an agent's HTML, run sandboxed, labelled outside what it draws, in its thread too. */
const app: Renderer = ofJson((data) => <AppArtifact data={data} />);

/** artifactr.ui's kinds and their renderers, for an application's registry. */
export const UI_RENDERERS: readonly (readonly [string, Renderer])[] = [
  ["form", form],
  ["submission", submission],
  ["dashboard", dashboard],
  ["app", app],
];
