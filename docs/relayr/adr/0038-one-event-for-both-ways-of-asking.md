# ADR-0038: One event for both ways of asking

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland

## Context

artifactr's forms ([artifactr ADR-0074](../../artifactr/adr/0074-forms-and-dashboards-in-artifactr-ui-behind-the-forms-extra.md)) are asked two ways: `ask_form` pauses a run, and a form artifact takes submissions. [lattice RFC-0005](../../rfcs/0005-forms-dashboards-and-mini-apps.md)'s U2 recommended one event, `ui:form_submitted`, through relayr's projections, which gained a mapping per deferred tool name ([ADR-0018](0018-bridged-events-their-fields-ids-and-projections.md), as amended). A client must not be able to publish one itself. artifactr can't depend on relayr, so the events and projections are relayr's.

## Decision

- **They are `relayr.ui`, behind relayr's `forms` extra,** `relayr-ai[forms]`, which requires `artifactr-ai[forms]`. Only `relayr.ui` imports `artifactr.ui`, as the layering test holds, so relayr without the extra is as it was.
- **`UiEvent(Event, abstract=True, event_namespace="ui")`** carries `author`, `thread_id` and `values`. **`FormSubmitted`** (`ui:form_submitted`) adds `form_id` and `version` for a submission, or `turn_id` and `tool_call_id` for an answer, one pair and never both; **`AppSubmitted`** (`ui:app_submitted`) adds `app_id` and `version`. `UI_EVENTS` holds both.
- **`UI_PROJECTIONS` is a typed dict of relayr's `Projections` arguments,** `artifacts` (`submission`) and `deferred` (`ask_form`), so `Projections(**UI_PROJECTIONS)` takes both, and an application merges each with its own of that name. A submission's `artifact_created` becomes the event; its `artifact_changed` and `artifact_archived` become nothing; an answer replaces `artifactr:deferred_answered` for that tool.
- **A submission's `thread_id` is its command's,** the thread it was sent in: a projection is a function of its envelope, and reads nothing else.
- **`UI_PUBLISHERS = {"ui": (SourceActor(name="artifactr"),)}`,** read-only, for reflexr's `publishers=` ([reflexr ADR-0057](../../reflexr/adr/0057-reserved-publishers.md)): relayr's follower publishes as that actor, and no one else may publish a `ui:` event.

## Consequences

- Easier: a rule is written once for both ways of asking, and reacts once to each, since relayr keeps the envelope's id.
- Harder: a submission's own artifact events don't reach rules as `artifactr:artifact_*`.
- Harder: relayr's floors on artifactr, `artifactr-ai>=0.2.0` and `forms = ["artifactr-ai[forms]>=0.2.0"]`, name a release without `DeferredAnswered.tool_name` or `artifactr.ui`, and can't rise in the change that adds them: uv locks no floor above a workspace member's own version. relayr's next release pull request stays unqueued until artifactr's next release is on `main`, and both floors rise to it first, as lattice [ADR-0023](../../adr/0023-publishing-to-pypi-from-the-release-workflow.md#amendment-2026-10-17-a-package-added-unreleased)'s amendment holds `artifactr-files-ai`'s release. A wheel published sooner would install against an artifactr that bridges no answer's tool and has no forms.
