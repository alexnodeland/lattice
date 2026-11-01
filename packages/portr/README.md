# portr

One gateway that serves lattice's commands to outside clients: Claude Desktop, claude.ai, ChatGPT, Cursor, Zed and terminals, over MCP, and coding agents over ACP. Every call goes through lattice-core's enforcer, so a client acting for a person does only what that person may, and asks them whatever they would be asked ([lattice RFC-0014](https://lattice.alexnodeland.com/rfcs/0014-portr-the-command-catalog-and-the-mcp-acp-gateway/)).

portr reaches the libraries' commands only through lattice-core's registry. It imports none of artifactr, reflexr, evalr or relayr.

🚧 **Being built.** This release holds `portr.core`, which turns the composed commands into the tools and resource templates a client is offered, for the toolsets its connection may use. The MCP server, OAuth with Supabase Auth, connections, limits and approvals by elicitation follow ([#917](https://github.com/alexnodeland/lattice/issues/917), [#918](https://github.com/alexnodeland/lattice/issues/918)).

```bash
uv add portr-ai      # imported as portr
```

Documentation: <https://lattice.alexnodeland.com/portr/>.
