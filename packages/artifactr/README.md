# artifactr

A Python library for building chat applications in which people and agents collaborate through **shared, mutually editable artifacts**.

The chat is one channel. The artifacts (documents, plans, specs, anything with structure) are a second one. artifactr makes every edit to them versioned, attributed, visible to every participant, and fed back into the agent's context, so each side can see how the other is thinking.

> **Status:** pre-release. The design is accepted and being built in the phases tracked by [RFC-0001](docs/rfcs/0001-v0.1-implementation-plan.md); the API below is the target.

## A taste of the API

```python
class Plan(Artifact):  # a Pydantic model; registered as "plan"
    write_policy: ClassVar[WritePolicy] = "propose"
    tasks: dict[str, Task] = {}

    def render_for_agent(self) -> str: ...


agent = Agent(
    "anthropic:claude-sonnet-5-5",
    deps_type=Session[AppDeps],
    toolsets=[plan_tools],
    capabilities=[ArtifactWorkspace(types=[Doc, Plan])],
)
runner = Runner(agent, app=AppDeps())

ws = await workspaces.open(tenant_id, workspace_id, actor=user)
plan = await ws.get(Plan, plan_id)
await ws.commit(plan.edit(lambda p: p.add_task("Ship v1")))  # versioned, attributed, published
await runner.send(ws, thread_id, "Break the launch into tasks")  # the agent sees what changed
```

## Documentation

- [Architecture](docs/architecture.md): concepts, layers, the write path, the agent, tenancy and concurrency.
- [Thread protocol v1](docs/protocol.md): the WebSocket, REST and MCP contracts (draft).
- [Architecture decision records](docs/adr/README.md): why each part is the way it is.
- [RFCs](docs/rfcs/README.md): proposals and the v0.1 build plan.

## Built on

[Pydantic](https://docs.pydantic.dev), [pydantic-ai](https://ai.pydantic.dev), [SQLAlchemy](https://www.sqlalchemy.org), [FastAPI](https://fastapi.tiangolo.com) and the [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, the trunk-based workflow, and the RFC and ADR process.

## License

[MIT](LICENSE)
