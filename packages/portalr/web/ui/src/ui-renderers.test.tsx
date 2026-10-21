import { describe, expect, test, vi } from "vitest";
import { render } from "vitest-browser-react";
import type { Submission } from "./artifactr-ui";
import { ArtifactContent, type Data, type Renderers } from "./artifacts";
import { IntegrationsContext } from "./integrations";
import { submissionId } from "./submission-id";
import { SUPPORT } from "./test/dashboards";
import { type FormHost, FormHostContext, UI_RENDERERS } from "./ui-renderers";

const RENDERERS: Renderers = new Map(UI_RENDERERS);

type Settled = Awaited<ReturnType<FormHost["submit"]>>;

const POLL: Data = {
  title: "Lunch",
  schema: {
    type: "object",
    properties: { dish: { type: "string", title: "Dish", enum: ["Soup", "Salad"] } },
    required: ["dish"],
  },
  ui: { submit_label: "Vote" },
  submissions: "once",
  closed: false,
};

/** A host whose submissions end as `settled`, and what it was asked to send. */
function host(settled: Settled = { outcome: "done" }, form: FormHost["form"] = () => null) {
  const submit = vi.fn(async (_id: string, _submission: Submission) => settled);
  return { principal: "user:alice", submit, form } satisfies FormHost;
}

/** A form artifact's page: its content, with its id and version, under a host. */
function Page({
  data = POLL,
  version = 2,
  hosted,
}: {
  data?: Data;
  version?: number;
  hosted: FormHost | null;
}) {
  return (
    <FormHostContext value={hosted}>
      <ArtifactContent
        kind="form"
        data={data}
        shown={{ id: "form_poll", version }}
        renderers={RENDERERS}
      />
    </FormHostContext>
  );
}

describe("a form", () => {
  test.each([
    ["once", ["form_poll"]],
    ["per_person", ["form_poll", "user:alice"]],
  ] as const)(
    "answered %s, is sent as a submission whose id is derived",
    async (submissions, parts) => {
      const hosted = host();
      const screen = await render(<Page hosted={hosted} data={{ ...POLL, submissions }} />);
      await screen.getByRole("radio", { name: "Salad" }).click();
      await screen.getByRole("button", { name: "Vote" }).click();
      const whose =
        parts.length === 1
          ? ({ submissions: "once" } as const)
          : ({ submissions: "per_person", principal: "user:alice" } as const);
      expect(hosted.submit).toHaveBeenCalledExactlyOnceWith(
        await submissionId("form_poll", whose),
        {
          form_id: "form_poll",
          version: 2,
          values: { dish: "Salad" },
        },
      );
    },
  );

  test("answered any number of times, each submit has its own nonce, kept for a retry", async () => {
    const hosted = host({ outcome: "closed" });
    const screen = await render(<Page hosted={hosted} data={{ ...POLL, submissions: "many" }} />);
    await screen.getByRole("radio", { name: "Soup" }).click();
    await screen.getByRole("button", { name: "Vote" }).click();
    await screen.getByRole("button", { name: "Vote" }).click();
    const [first, again] = hosted.submit.mock.calls;
    expect(again).toEqual(first);
    const nonce = first?.[1].nonce ?? "";
    expect(first?.[0]).toBe(await submissionId("form_poll", { submissions: "many", nonce }));
  });

  test("answered any number of times, a retry whose id is in use was sent", async () => {
    const hosted = host({ outcome: "refused", result: { rejection: { type: "invalid_state" } } });
    const screen = await render(<Page hosted={hosted} data={{ ...POLL, submissions: "many" }} />);
    await screen.getByRole("radio", { name: "Soup" }).click();
    await screen.getByRole("button", { name: "Vote" }).click();
    await expect.element(screen.getByRole("status")).toHaveTextContent("Sent.");
  });

  test("answered any number of times, another is sent with a new nonce", async () => {
    const hosted = host();
    const screen = await render(<Page hosted={hosted} data={{ ...POLL, submissions: "many" }} />);
    await screen.getByRole("radio", { name: "Soup" }).click();
    await screen.getByRole("button", { name: "Vote" }).click();
    await screen.getByRole("button", { name: "Send another" }).click();
    await screen.getByRole("radio", { name: "Salad" }).click();
    await screen.getByRole("button", { name: "Vote" }).click();
    const [first, second] = hosted.submit.mock.calls.map(([, submission]) => submission.nonce);
    expect(first).not.toBe(second);
  });

  test("refused as answered, it says so in place of its fields", async () => {
    const hosted = host({
      outcome: "refused",
      result: { rejection: { type: "invalid_state", message: "sub_1 already exists" } },
    });
    const screen = await render(
      <Page hosted={hosted} data={{ ...POLL, submissions: "per_person" }} />,
    );
    await screen.getByRole("radio", { name: "Soup" }).click();
    await screen.getByRole("button", { name: "Vote" }).click();
    await expect
      .element(screen.getByRole("status"))
      .toHaveTextContent("You've answered this form.");
    await expect.element(screen.getByRole("radio", { name: "Soup" })).not.toBeInTheDocument();
  });

  test("refused as changed, or shown at a new version, it says it changed and shows itself as it is", async () => {
    const hosted = host({
      outcome: "refused",
      result: {
        rejection: {
          type: "invalid_state",
          message:
            "form form_poll changed: the submission was made against version 2, and it is at 3",
          reason: "changed",
          artifact_id: "form_poll",
          version: 2,
          head: 3,
        },
      },
    });
    const screen = await render(<Page hosted={hosted} />);
    await screen.getByRole("radio", { name: "Soup" }).click();
    await screen.getByRole("button", { name: "Vote" }).click();
    await expect
      .element(screen.getByRole("status"))
      .toHaveTextContent(
        "This form changed since you opened it. It's shown as it is now: check your answers.",
      );
    await expect.element(screen.getByRole("button", { name: "Vote" })).toBeVisible();
    const later = await render(<Page hosted={host()} version={1} />);
    await later.getByRole("radio", { name: "Salad" }).last().click();
    await later.rerender(<Page hosted={host()} version={3} />);
    // What the person entered is kept, for them to check against the form as it is now.
    await expect.element(later.getByRole("radio", { name: "Salad" }).last()).toBeChecked();
    await expect
      .element(later.getByText(/This form changed since you opened it/).last())
      .toBeVisible();
  });

  test("refused as closed, it says so in place of its fields", async () => {
    const hosted = host({
      outcome: "refused",
      result: {
        rejection: {
          type: "invalid_state",
          message: "form form_poll is closed",
          reason: "closed",
          artifact_id: "form_poll",
        },
      },
    });
    const screen = await render(<Page hosted={hosted} />);
    await screen.getByRole("radio", { name: "Soup" }).click();
    await screen.getByRole("button", { name: "Vote" }).click();
    await expect.element(screen.getByRole("status")).toHaveTextContent("This form is closed.");
  });

  test("refused as off, it says forms are off, keeps what was entered, and offers no retry", async () => {
    const hosted = host({
      outcome: "refused",
      result: {
        rejection: {
          type: "not_enabled",
          message: "ui:forms is not available in this workspace",
          integration: "ui:forms",
        },
      },
    });
    const screen = await render(<Page hosted={hosted} />);
    await screen.getByRole("radio", { name: "Soup" }).click();
    await screen.getByRole("button", { name: "Vote" }).click();
    await expect
      .element(screen.getByRole("status"))
      .toHaveTextContent("Not available in this workspace: forms are off. This can't be sent.");
    await expect.element(screen.getByRole("radio", { name: "Soup" })).toBeChecked();
    await expect.element(screen.getByRole("radio", { name: "Soup" })).toBeDisabled();
    await expect.element(screen.getByRole("button", { name: "Vote" })).not.toBeInTheDocument();
  });

  test("with forms off in the workspace, it shows its fields, unsendable, and says so", async () => {
    const screen = await render(
      <IntegrationsContext value={(key) => key !== "ui:forms"}>
        <Page hosted={host()} />
      </IntegrationsContext>,
    );
    await expect
      .element(screen.getByRole("status"))
      .toHaveTextContent("Not available in this workspace: forms are off. This can't be sent.");
    await expect.element(screen.getByRole("radio", { name: "Soup" })).toBeDisabled();
    await expect.element(screen.getByRole("button", { name: "Vote" })).not.toBeInTheDocument();
  });

  test("refused as off for another integration, it names that one", async () => {
    const hosted = host({
      outcome: "refused",
      result: { rejection: { type: "not_enabled", integration: "ui:dashboards" } },
    });
    const screen = await render(<Page hosted={hosted} />);
    await screen.getByRole("radio", { name: "Soup" }).click();
    await screen.getByRole("button", { name: "Vote" }).click();
    await expect
      .element(screen.getByRole("status"))
      .toHaveTextContent(
        "Not available in this workspace: dashboards are off. This can't be sent.",
      );
  });

  test("refused as off for an integration not ui's, it says it isn't available, without a name", async () => {
    const hosted = host({
      outcome: "refused",
      result: { rejection: { type: "not_enabled", integration: "excalidraw" } },
    });
    const screen = await render(<Page hosted={hosted} />);
    await screen.getByRole("radio", { name: "Soup" }).click();
    await screen.getByRole("button", { name: "Vote" }).click();
    await expect
      .element(screen.getByRole("status"))
      .toHaveTextContent("Not available in this workspace. This can't be sent.");
  });

  test("refused as off, it can be sent again once the page's integrations are read anew", async () => {
    const hosted = host({
      outcome: "refused",
      result: { rejection: { type: "not_enabled", integration: "ui:forms" } },
    });
    const read = (on: boolean) => (key: string) => on || key !== "ui:forms";
    const screen = await render(
      <IntegrationsContext value={read(true)}>
        <Page hosted={hosted} />
      </IntegrationsContext>,
    );
    await screen.getByRole("radio", { name: "Soup" }).click();
    await screen.getByRole("button", { name: "Vote" }).click();
    await expect.element(screen.getByRole("button", { name: "Vote" })).not.toBeInTheDocument();
    // Read again, off, then on once more, as an admin turns forms back on.
    await screen.rerender(
      <IntegrationsContext value={read(false)}>
        <Page hosted={hosted} />
      </IntegrationsContext>,
    );
    await expect.element(screen.getByRole("radio", { name: "Soup" })).toBeDisabled();
    await screen.rerender(
      <IntegrationsContext value={read(true)}>
        <Page hosted={hosted} />
      </IntegrationsContext>,
    );
    await expect.element(screen.getByRole("button", { name: "Vote" })).toBeEnabled();
    await expect.element(screen.getByRole("radio", { name: "Soup" })).toBeChecked();
  });

  test("refused for a reason it doesn't know, it says the server refused it", async () => {
    const hosted = host({
      outcome: "refused",
      result: { rejection: { type: "invalid_state", message: "x", reason: "frozen" } },
    });
    const screen = await render(<Page hosted={hosted} />);
    await screen.getByRole("radio", { name: "Soup" }).click();
    await screen.getByRole("button", { name: "Vote" }).click();
    await expect
      .element(screen.getByRole("alert"))
      .toHaveTextContent("That wasn't done: the server refused it.");
  });

  test("refused otherwise, it says the server refused it", async () => {
    const hosted = host({ outcome: "refused", result: { rejection: { type: "forbidden" } } });
    const screen = await render(<Page hosted={hosted} />);
    await screen.getByRole("radio", { name: "Soup" }).click();
    await screen.getByRole("button", { name: "Vote" }).click();
    await expect
      .element(screen.getByRole("alert"))
      .toHaveTextContent("That wasn't done: the server refused it.");
  });

  test("closed, it says so, and can't be sent", async () => {
    const screen = await render(<Page hosted={host()} data={{ ...POLL, closed: true }} />);
    await expect.element(screen.getByRole("status")).toHaveTextContent("This form is closed.");
    await expect.element(screen.getByRole("button")).not.toBeInTheDocument();
  });

  test("without a host or an artifact to send to, its fields are shown, read-only", async () => {
    const screen = await render(<Page hosted={null} />);
    await expect
      .element(screen.getByRole("status"))
      .toHaveTextContent("This form can't be sent from here.");
    await expect.element(screen.getByRole("radio", { name: "Soup" })).toBeDisabled();
    await expect.element(screen.getByRole("button", { name: "Vote" })).not.toBeInTheDocument();
    await screen.rerender(<ArtifactContent kind="form" data={POLL} renderers={RENDERERS} />);
    await expect
      .element(screen.getByRole("status"))
      .toHaveTextContent("This form can't be sent from here.");
    await expect.element(screen.getByRole("radio", { name: "Soup" })).toBeDisabled();
  });

  test("data that aren't a form say so, and show as JSON", async () => {
    const screen = await render(<Page hosted={host()} data={{ title: "Odd", schema: "none" }} />);
    await expect
      .element(screen.getByRole("status").filter({ hasText: "can't be shown here" }))
      .toHaveTextContent("This form can't be shown here. Its data are below.");
    // Its data as a tree, each key beside its value.
    await expect.element(screen.getByText('"none"')).toBeVisible();
  });

  test("is titled by its title, and changed line by line", () => {
    const renderer = RENDERERS.get("form");
    expect(renderer?.title(POLL)).toBe("Lunch");
    expect(renderer?.diff).toBe("lines");
    expect(renderer?.text(POLL)).toBe(JSON.stringify(POLL, null, 2));
  });
});

describe("a submission", () => {
  const show = (data: Data) =>
    render(<ArtifactContent kind="submission" data={data} renderers={RENDERERS} />);

  test("says what was sent, to which form and version, each value by its field", async () => {
    const screen = await show({
      form_id: "form_poll",
      version: 2,
      values: {
        dish: "Soup",
        extras: ["Bread", "Water"],
        urgent: false,
        count: 3,
        ok: true,
        raw: null,
      },
    });
    await expect.element(screen.getByText(/as it was at version 2/)).toBeVisible();
    await expect.element(screen.getByText("form_poll")).toHaveProperty("tagName", "CODE");
    const terms = screen
      .getByRole("term")
      .elements()
      .map((term) => term.textContent);
    const said = screen
      .getByRole("definition")
      .elements()
      .map((value) => value.textContent);
    expect(terms).toEqual(["dish", "extras", "urgent", "count", "ok", "raw"]);
    expect(said).toEqual(["Soup", "Bread, Water", "No", "3", "Yes", "null"]);
  });

  test("naming neither a form nor an app, nor a version, it says it was sent", async () => {
    const screen = await show({ values: { a: "x" } });
    await expect.element(screen.getByText("Sent.", { exact: true })).toBeVisible();
  });

  test("to an app, names the app; with nothing filled in, says so", async () => {
    const screen = await show({ app_id: "app_calc", version: 1, values: {} });
    await expect.element(screen.getByText("app_calc")).toBeVisible();
    await expect.element(screen.getByText("Nothing was filled in.")).toBeVisible();
  });

  test.each([{ values: [] }, { values: null }, {}])(
    "with values that aren't an object, %j, says so",
    async (data) => {
      const screen = await show(data);
      await expect
        .element(screen.getByRole("status").filter({ hasText: "can't be shown here" }))
        .toHaveTextContent("This submission can't be shown here. Its data are below.");
    },
  );
});

describe("a dashboard", () => {
  test("is its panels, its forms the host's to show", async () => {
    const form = vi.fn((id: string) => <p>The form {id}</p>);
    const screen = await render(
      <FormHostContext value={host(undefined, form)}>
        <ArtifactContent kind="dashboard" data={SUPPORT as unknown as Data} renderers={RENDERERS} />
      </FormHostContext>,
    );
    await expect.element(screen.getByRole("article", { name: "Open tickets" })).toBeVisible();
    await expect.element(screen.getByText("The form form_ack")).toBeVisible();
  });

  test("with dashboards off, it still shows its snapshot, and its forms can't be sent", async () => {
    const form = (id: string) => (
      <ArtifactContent kind="form" data={POLL} shown={{ id, version: 1 }} renderers={RENDERERS} />
    );
    const screen = await render(
      <IntegrationsContext value={(key) => key !== "ui:dashboards"}>
        <FormHostContext value={host(undefined, form)}>
          <ArtifactContent
            kind="dashboard"
            data={SUPPORT as unknown as Data}
            renderers={RENDERERS}
          />
        </FormHostContext>
      </IntegrationsContext>,
    );
    await expect.element(screen.getByRole("article", { name: "Open tickets" })).toBeVisible();
    await expect
      .element(screen.getByRole("status"))
      .toHaveTextContent(
        "Not available in this workspace: dashboards are off. This can't be sent.",
      );
    await expect.element(screen.getByRole("radio", { name: "Soup" })).toBeDisabled();
    await expect.element(screen.getByRole("button", { name: "Vote" })).not.toBeInTheDocument();
  });

  test("without a host, its forms say they can't be shown; a panel it can't read is counted", async () => {
    const data = { ...SUPPORT, panels: [...SUPPORT.panels, { type: "map" }] } as unknown as Data;
    const screen = await render(
      <ArtifactContent kind="dashboard" data={data} renderers={RENDERERS} />,
    );
    await expect.element(screen.getByText(/which can't be shown here/)).toBeVisible();
    await expect.element(screen.getByText("One panel can't be shown here.")).toBeVisible();
  });

  test("data that aren't a dashboard say so", async () => {
    const screen = await render(
      <ArtifactContent kind="dashboard" data={{ panels: 1 }} renderers={RENDERERS} />,
    );
    await expect
      .element(screen.getByRole("status").filter({ hasText: "can't be shown here" }))
      .toHaveTextContent("This dashboard can't be shown here. Its data are below.");
  });
});

describe("an app", () => {
  test("shown without knowing which it is, as a preview is, is its label and summary alone", async () => {
    const screen = await render(
      <ArtifactContent
        kind="app"
        data={{ title: "Tip", summary: "Splits a bill.", html: "<script>x()</script>" }}
        renderers={RENDERERS}
      />,
    );
    const app = screen.getByRole("region", { name: "Tip" });
    await expect.element(app.getByText(/Made by the agent\. Runs sandboxed/)).toBeVisible();
    await expect.element(app.getByText("Splits a bill.")).toBeVisible();
    expect(app.element().querySelector("iframe, script")).toBeNull();
    expect(app.element().textContent).not.toContain("x()");
  });

  test("that can't be read is said to be so, with its data", async () => {
    const screen = await render(
      <ArtifactContent kind="app" data={{ summary: "" }} renderers={RENDERERS} />,
    );
    expect(screen.container.querySelector("iframe")).toBeNull();
    await expect
      .element(screen.getByRole("status").filter({ hasText: "can't be shown here" }))
      .toHaveTextContent("This app can't be shown here. Its data are below.");
  });
});
