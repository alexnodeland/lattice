/**
 * The compositions the screenshot suites shoot and the computed-style snapshots read: the frame with
 * its components, the controls, a thread, and the statuses and tables (portalr ADR-0019, ADR-0056).
 */

import type { Artifactr, ArtifactrV1 } from "@portalr/client";
import {
  House,
  KeyRound,
  Maximize2,
  MessageSquare,
  Play,
  Plus,
  ScrollText,
  ThumbsUp,
  Zap,
} from "lucide-react";
import { AccountMenu } from "../account-menu";
import { Alert } from "../alert";
import { AppShell } from "../app-shell";
import { Breadcrumbs } from "../breadcrumbs";
import { Button, type ButtonVariant } from "../button";
import { Card } from "../card";
import { Message, Messages, Streaming } from "../chat";
import { Checkbox, CheckboxGroup } from "../checkbox";
import { CodeBlock } from "../code-block";
import { ConfirmDialog } from "../confirm-dialog";
import { CopyButton } from "../copy-button";
import { Dialog } from "../dialog";
import { EmptyState } from "../empty-state";
import { Icon } from "../icon";
import { IconButton } from "../icon-button";
import { Menu } from "../menu";
import { PageHeader } from "../page-header";
import { Progress } from "../progress";
import { Questions } from "../questions";
import { Row, RowLink, Rows } from "../rows";
import { RunFailed } from "../run-failed";
import { SectionTitle } from "../section-title";
import { SegmentedFilter } from "../segmented-filter";
import { SelectField } from "../select-field";
import { NavLink, SideNav } from "../side-nav";
import { Reading, Skeleton } from "../skeleton";
import { StatCard } from "../stat-card";
import { StatusBadge, type Tone } from "../status-badge";
import { Switch } from "../switch";
import { Switcher, TenantSwitcher } from "../switcher";
import { TabLink, TabNav } from "../tab-nav";
import { Table } from "../table";
import { TextArea } from "../text-area";
import { TextField } from "../text-field";
import { TextLink } from "../text-link";
import { ToolCall, ToolCalls } from "../tool-call";

export function Gallery() {
  return (
    <AppShell
      home={<a href="#home" />}
      switcher={
        <Switcher
          tenant="acme"
          workspace="notes"
          tenants={[{ id: "acme" }, { id: "globex" }]}
          workspaces={[
            { id: "notes", detail: "4 threads" },
            { id: "support", detail: "12 threads" },
          ]}
          onTenant={() => undefined}
          onWorkspace={() => undefined}
        />
      }
      account={
        <AccountMenu
          name="Alex Nodeland"
          appearance="system"
          colourBlind={false}
          onColourBlind={() => undefined}
          onAppearance={() => undefined}
          onSignOut={() => undefined}
        />
      }
      nav={
        <SideNav label="Workspace">
          <NavLink href="#threads" icon={MessageSquare} count={1}>
            Threads
          </NavLink>
          <NavLink href="#artifacts" icon={ScrollText}>
            Artifacts
          </NavLink>
          <NavLink href="#runs" icon={Play} aria-current="page">
            Runs
          </NavLink>
          <NavLink href="#rules" icon={Zap}>
            Rules
          </NavLink>
        </SideNav>
      }
    >
      <PageHeader
        title="Runs"
        meta="The agent's turns and the rules' runs, newest first"
        actions={
          <SegmentedFilter
            label="Show"
            segments={[
              { value: "all", label: "All", count: 3 },
              { value: "you", label: "Needs you", count: 1 },
            ]}
            value="all"
            onValueChange={() => undefined}
          />
        }
      />
      <div className="flex flex-col gap-6">
        <Table caption="Runs">
          <thead>
            <tr>
              <th scope="col">Status</th>
              <th scope="col">Run</th>
              <th scope="col">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>
                <StatusBadge tone="waiting">Waiting for you</StatusBadge>
              </td>
              <td>Launch plan</td>
              <td>
                <Button variant="secondary">Answer</Button>
              </td>
            </tr>
            <tr>
              <td>
                <StatusBadge tone="failed">Dead-lettered</StatusBadge>
              </td>
              <td className="font-mono">portalr:triage</td>
              <td>
                <Button>Retry</Button>
              </td>
            </tr>
            <tr>
              <td>
                <StatusBadge tone="done">Done</StatusBadge>
              </td>
              <td>Move the launch</td>
              <td>
                <Button variant="ghost" aria-pressed>
                  Helpful
                </Button>
              </td>
            </tr>
          </tbody>
        </Table>
        <Card className="flex flex-col gap-3">
          <p>The agent wants to run publish.</p>
          <TextField label="Why? (optional)" defaultValue="The ticket had no subject" />
          <span className="flex gap-2">
            <Button>
              <Icon icon={Plus} />
              Approve
            </Button>
            <Button variant="secondary">Deny</Button>
            <Button disabled>Send</Button>
          </span>
        </Card>
        <Card className="flex flex-wrap items-center gap-3">
          <StatusBadge tone="near">Near budget</StatusBadge>
          <StatusBadge tone="over">Over budget</StatusBadge>
          <ConfirmDialog
            label="Delete acme"
            title="Delete acme?"
            confirm="Delete the tenant"
            typed="acme"
            onConfirm={async () => undefined}
          >
            Its 6 workspaces, their threads, artifacts and rules, and its 14 members' access go.
          </ConfirmDialog>
        </Card>
        <EmptyState title="No artifacts yet" action={<Button>Start a thread</Button>}>
          An artifact appears here when the agent makes one.
        </EmptyState>
      </div>
    </AppShell>
  );
}

/** A dialog over the frame, as a thread's sharing opens one. */
export function Sharing() {
  return (
    <Dialog
      open
      onOpenChange={() => undefined}
      title="Share the thread"
      description="Who holds a role on it."
    >
      <TextField label="Person" defaultValue="bob" />
    </Dialog>
  );
}

/** admin's frame, with its tenant switch and Home's cards, each in a state it can show. */
export function AdminGallery() {
  return (
    <AppShell
      ui="admin"
      home={<a href="#home" />}
      switcher={
        <TenantSwitcher
          tenant="acme"
          tenants={[{ id: "acme" }, { id: "globex" }]}
          onTenant={() => undefined}
          everyTenant={<a href="#deployment" />}
        />
      }
      account={
        <AccountMenu
          name="Alex Nodeland"
          appearance="system"
          colourBlind={false}
          onColourBlind={() => undefined}
          onAppearance={() => undefined}
          onSignOut={() => undefined}
        />
      }
      nav={
        <SideNav label="Tenant">
          <NavLink href="#home" icon={House} aria-current="page">
            Home
          </NavLink>
          <NavLink href="#access" icon={KeyRound}>
            Access
          </NavLink>
        </SideNav>
      }
    >
      <PageHeader title="acme" meta="How the tenant is doing" />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <StatCard title="Members" figure="5">
          4 people and 1 service principal
        </StatCard>
        <StatCard title="Feedback" figure="1,000+">
          pieces of feedback in the last week; 640 of 800 thumbs up
        </StatCard>
        <StatCard
          title="Spend"
          figure="$85.00"
          badge={<StatusBadge tone="near">Near budget</StatusBadge>}
        >
          of $100.00, every 30 days
        </StatCard>
        <StatCard
          title="Failed turns"
          figure={null}
          badge={<StatusBadge tone="failed">Unavailable</StatusBadge>}
        >
          Prometheus isn't answering: timed out
        </StatCard>
        <StatCard title="Workspaces" figure={null} busy>
          Reading…
        </StatCard>
      </div>
    </AppShell>
  );
}

const VARIANTS: readonly ButtonVariant[] = [
  "primary",
  "secondary",
  "ghost",
  "danger",
  "danger-soft",
];
const ROLES = [
  { value: "", label: "Choose a role…" },
  { value: "viewer", label: "viewer" },
  { value: "editor", label: "editor" },
  { value: "owner", label: "owner" },
];

export function Controls() {
  return (
    <div data-testid="controls" className="flex flex-col gap-6 bg-paper p-4 text-fg">
      <Card className="flex flex-col gap-3">
        <SegmentedFilter
          label="Window"
          showLabel
          hint="Whole days, in UTC."
          segments={[
            { value: "7", label: "7 days" },
            { value: "30", label: "30 days" },
            { value: "90", label: "90 days" },
          ]}
          value="30"
          onValueChange={() => undefined}
        />
        <SelectField label="Role" options={ROLES} hint="What they may do." defaultValue="editor" />
        <SelectField label="To" options={ROLES} disabled />
        <TextField
          label="Workspace"
          hint="A name from the list, or your own."
          defaultValue="notes"
        />
        <TextField label="Email" error="That isn't an email address." defaultValue="alice@" />
      </Card>
      <Card className="flex flex-col gap-3">
        {(["md", "sm"] as const).map((size) => (
          <div key={size} className="flex flex-wrap items-center gap-2">
            {VARIANTS.map((variant) => (
              <Button key={variant} variant={variant} size={size}>
                {variant}
              </Button>
            ))}
            <Button size={size} disabled>
              disabled
            </Button>
            <Button size={size} variant="secondary" disabled>
              disabled
            </Button>
          </div>
        ))}
      </Card>
      <Card className="flex flex-wrap items-center justify-between gap-2">
        <span>
          portalr:triage <span className="text-muted">run_dead</span>
        </span>
        <span className="flex gap-1">
          <ConfirmDialog
            label="Retry"
            about="run run_dead"
            look="ghost"
            size="sm"
            calm
            title="Retry?"
            confirm="Retry run"
            onConfirm={async () => undefined}
          >
            It runs again.
          </ConfirmDialog>
          <ConfirmDialog
            label="Skip"
            about="run run_dead"
            look="ghost"
            size="sm"
            title="Skip?"
            confirm="Skip run"
            onConfirm={async () => undefined}
          >
            It is given up on.
          </ConfirmDialog>
          <ConfirmDialog
            label="Cancel"
            about="run run_dead"
            look="danger-soft"
            size="sm"
            dismiss="Keep running"
            title="Cancel this run?"
            confirm="Cancel run"
            onConfirm={async () => undefined}
          >
            It is stopped.
          </ConfirmDialog>
        </span>
      </Card>
    </div>
  );
}

const sent = async () => ({ outcome: "done" }) as const;

const message = (id: string, content: string, user: boolean): Artifactr.Message => ({
  id,
  seq: 1,
  actor: user ? { kind: "user", id: "alice" } : { kind: "agent", thread_id: "t", run_id: "r" },
  content,
  kind: "message",
  runId: user ? null : "r",
  feedback: [],
});

const ASKED: ArtifactrV1.DeferredRequest = {
  kind: "question",
  tool_call_id: "q1",
  tool_name: "ask_user",
  args: {
    questions: [
      {
        question: "Which week should the launch note cover?",
        header: "Launch week",
        options: [
          { label: "This week", description: "The current week", recommended: true },
          { label: "Next week", description: "The following week" },
        ],
        other: true,
      },
      {
        question: "Which topics should it cover?",
        header: "Topics",
        options: [
          { label: "What shipped", description: "Highlights and scope", recommended: true },
          { label: "Metrics", description: "Adoption and feedback" },
          { label: "Next steps", description: "What comes after" },
        ],
        multiple: true,
      },
    ],
  } as ArtifactrV1.Args,
};

const tool = (name: string, status: string, result: string): Artifactr.Tool => ({
  name,
  status,
  args: '{"kind": "note", "data": {"text": "Launching next week."}}',
  result,
  argsCut: false,
  resultCut: false,
  seq: 1,
});

export function Thread() {
  return (
    <div data-testid="chat" className="flex flex-col gap-6 bg-paper p-4 text-fg">
      <Messages>
        <Message message={message("m1", "Draft the launch note.", true)} author="You" mine />
        <li>
          <Questions request={ASKED} onAnswer={sent} focus={false} />
        </li>
        <ToolCalls>
          <ToolCall tool={tool("create_artifact", "ok", "Done: note_1 is now at version 1.")} />
          <ToolCall tool={tool("draft_rule", "retry", "rule\n  Input should be an object")} />
        </ToolCalls>
        <Message
          message={message("m2", "The launch note is **drafted**.", false)}
          author="Assistant"
          onThumbs={sent}
        />
        <Message message={message("m3", "Thanks!", true)} author="You" mine sending />
        <Streaming text="" author="Assistant" />
      </Messages>
    </div>
  );
}

export function Ended() {
  return (
    <div data-testid="chat" className="flex flex-col gap-6 bg-paper p-4 text-fg">
      <Messages>
        <li>
          <Questions
            request={ASKED}
            answer={{
              answers: [
                { selected: [], other: "The week of 2 November" },
                { selected: ["What shipped", "Metrics"] },
              ],
            }}
            answeredBy="You"
            onAnswer={sent}
          />
        </li>
        <RunFailed
          reason="tool_retries_exhausted"
          error="Tool 'draft_rule' exceeded max retries count of 3"
          onRetry={sent}
        />
      </Messages>
    </div>
  );
}

const TONES: readonly [Tone, string][] = [
  ["working", "Running"],
  ["waiting", "Waiting for you"],
  ["done", "Succeeded"],
  ["failed", "Dead-lettered"],
  ["retrying", "Retrying"],
  ["queued", "Queued"],
  ["stopped", "Cancelled"],
  ["near", "Near budget"],
  ["over", "Over budget"],
];

export function Sheet() {
  return (
    <div data-testid="sheet" className="flex flex-col gap-4 bg-paper p-4 text-fg">
      <div className="flex flex-wrap gap-2">
        {TONES.map(([tone, word]) => (
          <StatusBadge key={tone} tone={tone}>
            {word}
          </StatusBadge>
        ))}
      </div>
      <Alert tone="error">The tenant wasn't created: that name is taken.</Alert>
      <Alert tone="warn">
        These are the newest: there may be more. A shorter window finds the rest.
      </Alert>
      <Alert>Saved.</Alert>
      <Reading>Reading the workspace's runs…</Reading>
      <div className="grid grid-cols-2 gap-4">
        <StatCard
          title="Spend"
          figure="$85.00"
          badge={<StatusBadge tone="near">Near budget</StatusBadge>}
          action={<a href="#usage">Usage</a>}
        >
          of $100.00, every 30 days
        </StatCard>
        <StatCard
          title="Failed turns"
          figure="3"
          badge={<StatusBadge tone="failed">Unavailable</StatusBadge>}
        >
          agent turns in the last day, a line long enough to wrap
        </StatCard>
      </div>
      <Card>A card, raised a little.</Card>
    </div>
  );
}

export function Rowed({ ui }: { ui: "app" | "admin" }) {
  return (
    <AppShell
      ui={ui}
      home={<a href="#home" />}
      switcher={<span>acme</span>}
      account={<span>alice</span>}
    >
      <div data-testid="table">
        <Table caption="Members">
          <thead>
            <tr>
              <th scope="col">Member</th>
              <th scope="col">Kind</th>
              <th scope="col">Actions</th>
            </tr>
          </thead>
          <tbody>
            {["alice", "bob", "ci-bot"].map((name) => (
              <tr key={name}>
                <th scope="row">{name}</th>
                <td>person</td>
                <td>
                  <Button variant="danger-soft" size="sm">
                    Remove
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      </div>
    </AppShell>
  );
}

/**
 * The kit's other primitives, each in the states it shows: the checks, a switch, tabs, a text
 * area with a refusal, a text link, rows, what is being read, progress, a section's title, a menu's
 * trigger, a copy button, and the code block.
 */
export function Kit() {
  return (
    <div data-testid="kit" className="flex flex-col gap-4 bg-paper p-4 text-fg">
      <SectionTitle>The kit</SectionTitle>
      <span className="flex flex-wrap items-center gap-3">
        <Checkbox aria-label="Unchecked" />
        <Checkbox aria-label="Checked" defaultChecked />
        <Checkbox aria-label="Disabled" disabled />
        <Switch aria-label="Off" />
        <Switch aria-label="On" defaultChecked />
        <Switch aria-label="Off, disabled" disabled />
        <Switch aria-label="On, disabled" defaultChecked disabled />
      </span>
      <CheckboxGroup
        legend="Topics"
        choices={[
          { value: "shipped", label: "What shipped" },
          { value: "metrics", label: "Metrics" },
        ]}
        value={["shipped"]}
        onValueChange={() => undefined}
        hint="As many as fit."
      />
      <TabNav label="Sections">
        <TabLink href="#one" aria-current="page">
          One
        </TabLink>
        <TabLink href="#two">Two</TabLink>
      </TabNav>
      <TextArea label="Note" error="It can't be empty." defaultValue="" />
      <p>
        Read <TextLink href="#more">more about it</TextLink> or open{" "}
        <TextLink variant="external" href="https://example.com">
          Langfuse
        </TextLink>
        .
      </p>
      <TextLink variant="subtle" href="#trace">
        trace_1
      </TextLink>
      <TextLink variant="nav" href="#runs">
        Runs
      </TextLink>
      <Breadcrumbs
        trail={[
          { label: "Workspace", href: "#notes" },
          { label: "Threads", href: "#threads" },
        ]}
      />
      <Rows label="Threads">
        <Row
          name={<RowLink href="#a">Launch plan</RowLink>}
          meta="2 days ago"
          end={<StatusBadge tone="waiting">Waiting for you</StatusBadge>}
        />
        <Row name={<RowLink href="#b">Move the launch</RowLink>} />
      </Rows>
      <Skeleton className="h-4 w-32" />
      <Progress label="Checking in brief.docx" value={21} max={48} />
      <Menu label="Actions" items={[{ label: "Open", onSelect: () => undefined }]} />
      <CopyButton text="portalr" what="the name" />
      <span className="flex gap-1">
        <IconButton label="Helpful" icon={ThumbsUp} aria-pressed />
        <IconButton label="Full view" icon={Maximize2} />
      </span>
      <CodeBlock code={'const a = "b";'} language="text" />
    </div>
  );
}
