# The app

The app, at `/portalr/app/`, is the UI for the people who use your application: they chat with its agents and see their work. It is a thin client: the browser calls artifactr's, reflexr's and grantr's own routes, and shows only what grantr says the person may see and do. This page walks its areas ([ADR-0014](../adr/0014-the-apps-shell.md) through [ADR-0022](../adr/0022-restricting-and-sharing-a-thread.md) record how each is built).

## Tenants and workspaces

After [signing in](../getting-started.md#sign-in), the app lists the tenants the person belongs to, from grantr's `/me`. A person with one goes straight to it, and with none is told they have no access. In a tenant it lists the **workspaces** they can open: grantr filters artifactr's list by what each person may open, so a workspace they have no role in isn't there.

Everything below is inside a workspace, `/t/<tenant>/w/<workspace>`, whose artifactr and reflexr streams are open while any of its areas is, and close when the person leaves. The streams reconnect from where they were after a drop, and with each refreshed token.

## Threads

A workspace's threads, and a new one. A **thread** is a conversation, and its page is the chat:

- the messages, oldest first, and what an agent's run is streaming as it writes;
- a **tool call** the run made, and how it returned;
- what a **paused run waits on**: a call to approve or deny, or a question to answer;
- the thread's **proposals**, each with its rationale and how it was resolved, to accept or reject;
- a composer, only where grantr allows the person to post.

Markdown renders through Streamdown, with no raw HTML; links go to the web, mail, the page and the application only, and images only from the app's own origin. GitHub's callouts (`> [!NOTE]`, `[!TIP]`, `[!IMPORTANT]`, `[!WARNING]`, `[!CAUTION]`) show as notes with their word, and a block of code names its language, is highlighted in the common languages, and has **Wrap** and **Copy**. Math between `$$` shows as math, within a line or on lines of its own; a single `$` is a price. **Copy** under a message copies it as the Markdown it was written in. A Mermaid diagram shows as its source: diagrams aren't drawn yet.

### Restricting and sharing a thread

A thread's menu, "Thread actions", holds **Share…** and **Restrict** (or **Lift restriction**), shown only where grantr allows them on that thread. A restricted thread is hidden from everyone who doesn't hold a role on it. **Share…** lists who holds a role on the thread, each with Revoke where grantr allows it, and shares it with a person as a viewer or an editor. People are shown by email where the application names them ([Getting started](../getting-started.md#mount-the-router)), and otherwise by a short id; so is a message's author in the chat, unless they posted under a name of their own. If a thread is restricted while someone has it open, their page says "This isn't available to you any more" in place of the chat.

## Artifacts

The workspace's artifacts that aren't archived, each by kind and latest version. An artifact's page shows it through its kind's renderer, its **revisions** newest first with what each changed (a diff, marked for screen readers as well as by colour), and its open proposals. The app registers the template's `note` kind as Markdown; an application with kinds of its own adds its renderers to `src/renderers.ts` in `web/app`. A kind with no renderer shows as formatted JSON.

## Proposals

Every proposal in the workspace, the open ones first, each linking to the artifact it would change, to accept or reject. An agent only proposes changes to an artifact it may not edit; a person with the right accepts.

## Runs

The agent's **turns** and the rules' **runs**, newest first:

| What | Shows | Offers |
|---|---|---|
| A turn | Its thread and status | **Stop**, while it runs |
| A rule's run | Its rule, its attempt, how often it was retried, and *Dead-lettered* where it failed every attempt | **Retry** when dead-lettered, **Skip** when dead-lettered or retrying, **Cancel** when queued, running or retrying |

Each button shows only where grantr allows the action in that workspace: a viewer sees thumbs and none of them. Hiding a button is not the check: the server asks grantr again for every command.

**Thumbs** on a message, an artifact's version, or a run, with an optional comment, are the app's feedback. They go to the log, and an admin sees them in [Feedback](admin.md#feedback).

## Rules

The workspace's rules: code rules first, then stored ones, each with its origin, its version if stored, whether it is enabled, how far behind the log it is, and its dead letters. The schedules that tick into the workspace are listed with their next and last ticks, in the reader's time zone. A rule's page shows its description, origin and JSON.

Where grantr allows, a **stored rule** can be installed from reflexr's JSON, edited and saved, or archived. The browser checks only that the text is JSON; reflexr checks the rest, and its reasons are what the field says. An update names the version it replaces: a change made over someone else's is refused, and the page says which version was saved since, with a button that loads it. Renaming a rule is installing a new one. A code rule has none of these.

!!! note "Rules from chat"

    A person can ask the agent for a rule in a thread; it arrives as a proposal like any other change ([stackr's template](../../stackr/guides/template.md) enables it). The Rules area is where it is then read and managed.

## Colour-blind friendly charts

**Colour-blind friendly charts** is a switch in the account menu, under **Colour**, in this UI and in admin. It is a setting of this browser: it is kept in the browser's local storage as the scheme is, so it is not shared with the person's other browsers or devices, and it is applied before the page first paints, so it never flashes on after the page. With it on, the charts' series take a blue, an orange or yellow and a purple that stay apart to people who see no red, no green or no blue, and every series past the first is hatched, dashed in a line and marked with a shape of its own, so no series relies on its hue ([ADR-0036](../adr/0036-the-chart-theme-and-colour-blind-mode.md)). The status colours are the same in both modes: they hold their contrast to every reader, and each status is a word and a shape too. In a high-contrast mode (forced colours) the patterns are on whatever was chosen.

## What is not here

- **No other sign-in than a password** yet: magic links and your own providers are planned for phase 7 ([ADR-0014](../adr/0014-the-apps-shell.md)), and the template's portal, the first part of it, doesn't bring them.
