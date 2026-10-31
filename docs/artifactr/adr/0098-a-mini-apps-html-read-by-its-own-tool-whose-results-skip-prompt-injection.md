# ADR-0098: A mini app's HTML read by its own tool, whose results skip prompt-injection

**Status:** Accepted
**Date:** 2026-10-31
**Deciders:** Alex Nodeland

## Context

stackr's gateway runs `prompt-injection` on tool results only ([stackr ADR-0010's amendment](../../stackr/adr/0010-the-llm-gateway.md#amendment-2026-10-27-prompt-injection-reads-tool-results)). Its word lists treat a sentence holding "enter" and "unlimited" as a jailbreak, and a page of markup is a few very long sentences. `read_artifact` returned a mini app's whole HTML ([ADR-0082](0082-mini-apps-the-agents-tools-and-html-that-loads-nothing.md)), so an agent that read a generated app back could trip the guardrail. The result then stays in the thread's history, which every later request carries, so the thread is blocked for good ([#830](https://github.com/alexnodeland/lattice/issues/830)).

The proxy can't tell one tool's result from another's in a tool message, so the choice has to be the library's, per request. Since the history carries old results, it has to look at every tool result in the request, not just the newest. Only an agent writes an app's HTML; a person changes only its state. So the HTML is the model's own output, as its tool arguments are, which the proxy already leaves unscanned.

## Decision

- **`read_artifact` shows an app without its HTML.** `Artifact.render_for_tool()` is the text `read_artifact` returns. It defaults to `render_for_agent()`; `App` overrides it with the app's title, summary and state, and says to read the HTML with `read_app`. The agent's instructions, where the artifacts it follows are shown with `render_for_agent()`, keep the HTML, since the guardrail doesn't read them. So do the MCP server's `read_artifact` and the evaluators, which don't go through the gateway.
- **`read_app(id)` returns an app's HTML,** and nothing a person wrote. It's offered beside `create_app` and `update_app`, only while `ui:mini-apps` is on, and follows the app as `read_artifact` does.
- **The gateway leaves the tool-result guardrails out of a request whose every tool result came from an echo tool.** `LiteLLMGateway` takes `echo_tools`, defaulting to `ECHO_TOOLS`, `{"read_app"}`, and `tool_result_guardrails`, defaulting to `TOOL_RESULT_GUARDRAILS`, `{"prompt-injection"}`.
  - Before each request it reads every tool result in the messages, retries for a tool included. When there is at least one and each came from an echo tool, it removes those guardrails from what the workspace's policy names.
  - One result from any other tool keeps them, for the whole request, history and all.
  - A request with no tool result keeps them too, which changes nothing, since the proxy scans no request without one.

## Options considered

| Option | For | Against |
|---|---|---|
| **A tool of its own, exempted by name, and `read_artifact` without the HTML (chosen)** | An app read back, or read to change it, no longer blocks its thread | A thread that also holds an outside tool result is scanned whole, the app's HTML included |
| `read_artifact` without the HTML, and nothing else | No exemption at all | `update_app` takes the whole HTML, so changing an app made in another thread means reading it, and the block returns |
| Exempting `read_artifact` | One tool, no new one | Its results hold artifacts people and connectors wrote, untrusted text the guardrail is there for |
| Waiting for taint tracking ([#903](https://github.com/alexnodeland/lattice/issues/903)) | The real answer to untrusted content | Leaves threads blocked meanwhile |

## Consequences

- Easier: an agent reads an app back, or reads it to change it, without blocking its thread.
- Easier: the exemption covers only text an agent wrote, the same text the proxy already leaves unscanned in tool arguments.
- Harder: a thread whose history also holds an outside tool result, such as a fetched page, is still scanned whole, app HTML included, and can still be blocked. Taint tracking (#903), which follows untrusted content itself rather than matching words, is the lasting answer.
- Harder: an application with a tool of its own named `read_app` would have its results exempted; it passes `echo_tools` to name its own. Two tools of one name can't be offered to one agent, so only one `read_app` is ever in a request.
- Applications name more echo tools, or other tool-result guardrails, through `echo_tools` and `tool_result_guardrails`.
