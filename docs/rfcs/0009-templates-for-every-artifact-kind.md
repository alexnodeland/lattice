# RFC-0009: Templates for every artifact kind

**Status:** Draft
**Author:** Alex Nodeland
**Created:** 2026-10-28
**Discussion:** the pull request that adds this file

## Summary

A **template** is a versioned artifact that seeds a new artifact of one kind: a native file's bytes, or a note's, form's, dashboard's, diagram's or mini app's data, with written guidance for people and agents. Templates are scoped to a person, a group, a workspace, a tenant or the whole deployment, and lattice ships built-ins: two for every native file type that has a file format, and two for every other kind. People create from templates in portalr. Agents find templates, read their guidance and create from them, instead of starting blank. Workflows and skills can name the templates they create from. A new artifact records which template and version it came from, and is never changed by later versions of it.

Tracked by #1067.

## Motivation

Every artifact in lattice starts from nothing. An agent asked for a report calls `create_native_file(type, title)`, which makes a blank file, then writes the whole document as edits. A team with a house style for briefs, budgets, decks or drawings has no way to hand it to people or agents, and a good structure made last week can't be reused. The same is true of notes, forms, dashboards, diagrams and mini apps.

Templates give people and agents a starting point that carries structure and style, decided once and reused across the environment. They make agents' output consistent with the team's, and they make a new deployment useful on day one.

Why now: v0.3 adds skills (#959) and workflows (#965), which both need a scope model (thread to tenant) and a catalogue, and both produce artifacts. Designing templates beside them lets the three share one scope resolver and one catalogue, and lets workflows and skills name templates from the start.

## Design

### Scope and the owner's decisions

Decided by the owner (2026-10-28), and recorded here:

- **Every artifact kind, equally, in v0.3**: native files, notes, forms, dashboards, Excalidraw diagrams and mini apps.
- **Scopes**: personal, group, workspace and tenant, plus an operator's deployment catalogue and lattice's built-ins.
- **Style**: a template carries its own structure and styles, and **written guidance** that agents read. Drawing on tenant brand kits ([RFC-0007](0007-portalr-brand-kits.md)) waits until brand kits are per tenant.
- **Built-ins**: two for every native file type with a file format, and two for every other kind.
- **Placeholders in native files are filled by the agent**, through the file's app, after the copy. lattice never rewrites a native file's bytes itself.
- **In v0.3 too**: the operator's catalogue (#1073), templates named by workflows and skills (#1074), update notices (#1075), and agent-suggested templates (#1076).

### The template object

A `template` is an artifact kind in artifactr ([#1068](https://github.com/alexnodeland/lattice/issues/1068)):

```python
class Template(Artifact):
    """A versioned seed for a new artifact of one kind."""

    kind: ClassVar[str] = "template"
    write_policy: ClassVar[WritePolicy] = "propose"  # at tenant scope; see Publishing

    for_kind: str  # the kind it seeds: "word_document", "note", "form", ...
    name: str
    description: str = ""
    tags: list[str] = []
    guidance: str = ""  # Markdown for people and agents: structure, tone, length, what to fill
    placeholders: list[Placeholder] = []  # the names a seed uses, each with a label and a default
    seed: Seed  # NativeSeed (a blob reference and its app's inspection) or DataSeed (the kind's data)
    scope: Scope  # personal | group | workspace | tenant | deployment | builtin
    owner: str | None  # the user or group id, for personal and group scopes
```

- **Versioned like any artifact.** Each change is a new version; nothing made from it changes.
- **Validated on save**: a native seed is inspected by its app as an upload is, and refused if the app can't open it or it's over the type's size limit. A data seed is validated by its kind's schema. A form seed holds no submissions; a mini app seed holds no stored state.
- **A preview**: a native seed's first page, rendered and cached as a file's pages are; other kinds are drawn by their renderer.
- **Archived**, a template leaves every picker. Artifacts made from it are unaffected.

### Scopes and visibility

| Scope | Who sees it | Who changes it |
|---|---|---|
| `personal` | Its owner | Its owner, directly |
| `group` | The group's members | The group's template managers, directly |
| `workspace` | The workspace's readers | As the workspace's write policy says |
| `tenant` | The tenant's members | Through an accepted proposal, accepted by tenant admins |
| `deployment` | Every tenant the operator lists (#1073) | Operators alone, audited |
| `builtin` | Everyone, where the kind's app is on | Nobody: shipped with lattice, copied to change |

- **One resolver, shared with skills and workflows** (#962, #970): `visible(principal, kind) -> list[TemplateRef]`, decided by grantr's memberships, groups and grants, evaluated as every artifactr read is. An agent sees what the person it acts for sees; a key sees what its grants allow.
- **A tenant can hide** a deployment or built-in template from its pickers, and copy any template it can see into a scope it can write to.
- **Defaults**: a workspace or tenant setting ([lattice ADR-0030](../adr/0030-settings-typed-declared-in-lattice-core-and-only-narrowed-below.md)) names a default template per kind, which pickers offer first and agents use unless asked otherwise.

### Applying a template

`apply_template(template_id, version=None, title, thread_id=None, values={})` creates an artifact of the template's kind:

1. The seed is copied as the new artifact's first version: a native seed's blob is copied to a new blob, and inspected again; a data seed's data is copied.
2. **Data placeholders** (`{{title}}`, `{{date}}`, `{{author}}`, `{{workspace}}`, and those the template declares) are filled from `values` in data seeds, in text fields alone. Nothing else in a seed is expanded.
3. **Native placeholders** are filled after the copy, through the file's app: by the agent with `edit_native`, as it edits any file; for a person, the picker's short form produces the same command batch, run as an edit on their behalf. The copy is never rewritten byte by byte.
4. Provenance is `{source: "template", template_id, template_version}`, beside the app's details for a native file.

Creating from a template is applied as creating blank is today, as the person the caller acts for. Later edits follow the kind's write policy, so an agent's edits to a native file are still proposals.

### Agents

Tools behind the same switches as the kinds they create ([#1069](https://github.com/alexnodeland/lattice/issues/1069)):

| Tool | What it does |
|---|---|
| `find_templates(kind, query)` | The templates the person can see for a kind, best match first: name, scope, description, and whether it is the default |
| `read_template(template_id)` | Its guidance, its placeholders, and an outline of its seed |
| `create_native_file(type, title, template=None, values={})` | As now, or from a template |
| `create_artifact(kind, data=None, template=None, values={})` | As now, or from a template |

The agent's instructions: when asked to make a kind of artifact, look for a matching template first (the workspace's default if there is one), say which one it used, follow its guidance, and fill its placeholders. With no match, start blank, as now. The tools are served over MCP and ACP through portr, with the same permissions.

### Workflows and skills

A workflow step that creates an artifact takes `template: {id, version?}`, and the workflow's static checks (#966) reject a template that is missing, of another kind, archived at a pinned version, or not visible at the workflow's scope. A skill's manifest may name templates the agent uses when the skill is equipped (#1074). Unpinned references use the latest version; pinned ones reproduce the same output.

### portalr

([#1070](https://github.com/alexnodeland/lattice/issues/1070))

- **New from a template** wherever something can be made: blank first, then the templates grouped by scope, with search, previews, guidance and the placeholder form.
- **Save as a template** on any artifact a person can read, to a scope they can write to. For a tenant scope it opens a proposal instead.
- **A Templates area**: browse by kind and scope, preview, edit, see versions and what was made from each, archive, hide.
- **Admin**: tenant and deployment templates, their proposals, defaults per kind, and what is hidden.
- **Update notices** (#1075): an artifact made from an older version says "Made from Report v3; v5 is current" and offers a comparison of the two versions. Nothing changes automatically.

### Suggested templates

When a person or workspace makes several artifacts of one kind with a similar structure and no template covers it, the agent may propose a template (#1076). The draft keeps the structure and removes the content, and is offered only at a scope whose readers could read every source. Suggestions are proposals, at most one per person per week, never repeated for a kind dismissed in the last month, and can be turned off per workspace.

### Built-ins

- **Native files** ([#1071](https://github.com/alexnodeland/lattice/issues/1071)): two for each of the 14 types with a file format (LightCraft has none yet), 28 in all. For example: a project brief and a report (WordCraft), a budget and a project tracker (GridCraft), an update deck and a proposal pitch (DeckCraft), a product shot studio and a turntable (Blender).
- **Other kinds** ([#1072](https://github.com/alexnodeland/lattice/issues/1072)): two each, for example meeting notes and a decision record, a request intake and a feedback survey, weekly metrics and a support overview.
- **Licensing**: authored for lattice and released under MIT or CC0. Nothing inside a built-in (fonts, images, audio) may have a licence that forbids redistribution; each one's licences are recorded.
- **Checked in CI**: each native built-in is opened, inspected and rendered by its own app's worker, and its pages and outline are compared with what it declares; each other built-in is drawn by its renderer.
- **Shipped as data** with artifactr, installed as `builtin` templates, and offered only where the kind's app is switched on.

### Errors

| Case | Answer |
|---|---|
| The template isn't visible to the caller | `NotFound`, as for any hidden artifact |
| Its kind's app is off in the workspace | Refused, naming the switch, as creating blank is |
| Its seed no longer opens in the app (an app upgrade) | `AppFailed`, and the template is flagged for its owners |
| A placeholder value is missing | The placeholder's default, or left as written, said in the result |
| A pinned version is archived | Refused, in workflow checks and at run time |

## Drawbacks

- **Another kind with its own UI**, on every surface that makes artifacts.
- **Built-ins are real authoring work**, especially for the creative and CAD apps, and must be kept opening as the apps change.
- **Seeds can be large**: native templates hold whole files; size limits and copying blobs bound this, but storage grows with each version.
- **App upgrades can break templates** whose seeds an app no longer opens; CI catches the built-ins, but tenants' own need flagging.

## Alternatives

- **Templates for native files only**: every kind has the same need, and scopes, picker, versioning and saving would be built again for each.
- **A flag on any artifact marking it a template**: blurs a document with the template made from it, and makes scoping per artifact awkward.
- **Templates as files in a folder per deployment**: no scopes, no review, no personal templates.
- **Linked templates that push updates to what was made from them**: surprising, and fights with each artifact's own history; notices and comparisons give the benefit without that.
- **Placing template content in the agent's prompt**: costly, and loses a file's real styles; a seed copied as the first version keeps them.
- **lattice filling native placeholders by rewriting the file**: every format would need its own rewriter; the apps' own commands already edit them safely.

## Unresolved questions

- How a group names its template managers: a grantr role on the group, or the group's existing admins.
- Whether a workspace template's write policy should default to proposals, as a tenant's does.
- How many versions of a large native template are kept, beyond those something was made from.
- When per-tenant brand kits land, whether a template names a brand, or simply takes the tenant's.

## Tracking

- [ ] The template object, scopes and resolver, applying, and saving (#1068).
- [ ] Agent tools and instructions, over MCP and ACP (#1069).
- [ ] portalr: new from a template, save as a template, the Templates area and admin (#1070).
- [ ] Built-in native file templates, checked in CI (#1071).
- [ ] Templates for the other kinds, and their built-ins (#1072).
- [ ] The operator's catalogue (#1073).
- [ ] Templates in workflows and skills (#1074).
- [ ] Update notices (#1075).
- [ ] Agent-suggested templates (#1076).
