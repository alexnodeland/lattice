# artifactr

A Python library for building chat applications in which people and agents collaborate through **shared, mutually editable artifacts**.

The chat is one channel. The artifacts (documents, plans, specs, anything with structure) are a second one. artifactr makes every edit to them versioned, attributed, visible to every participant, and fed back into the agent's context, so each side can see how the other is thinking.

> **Status:** design accepted, implementation in progress. The code in `src/` is an earlier prototype that the new design replaces.

## A taste of the API

```python
class Plan(Artifact):  # a Pydantic model; registered as "plan"
    write_policy: ClassVar[WritePolicy] = "propose"
    tasks: dict[str, Task] = {}

    def render_for_agent(self) -> str: ...


agent = Agent(
    "anthropic:claude-sonnet-5-5",
    deps_type=Session[AppDeps],
    capabilities=[ArtifactWorkspace(types=[Doc, Plan], toolsets=[plan_tools])],
)

ws = await workspaces.open(tenant_id, workspace_id, actor=user)
plan = await ws.get(Plan, plan_id)
await ws.commit(plan.edit(lambda p: p.add_task("Ship v1")))  # versioned, attributed, published
```

## Documentation

- [Architecture](docs/architecture.md): concepts, layers, the write path, the agent, tenancy and concurrency.
- [Thread protocol v1](docs/protocol.md): the WebSocket, REST and MCP contracts (draft).
- [Architecture decision records](docs/adr/README.md): why each part is the way it is.

## Built on

[Pydantic](https://docs.pydantic.dev), [pydantic-ai](https://ai.pydantic.dev), [SQLAlchemy](https://www.sqlalchemy.org), [FastAPI](https://fastapi.tiangolo.com) and the [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk).
