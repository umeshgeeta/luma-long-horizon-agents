# Horizon

Horizon is the server in the middle. The supervisor and the Nimble wrapper are the only two clients, and they call different tools.

```mermaid
flowchart LR
  subgraph clients [Two clients]
    sup["Supervisor page<br/>list, timeline, compact, terminate"]
    wrap["Nimble wrapper<br/>register, append"]
    search[Nimble search]
  end

  subgraph horizon [Horizon]
    mcp[MCP server on HTTP]
    db[RawTree]
    model[LFM2.5]
  end

  sup -->|list_agents, get_timeline, compact, terminate_agent| mcp
  sup -->|starts| wrap
  wrap -->|register_agent, append_event| mcp
  wrap -->|search| search
  mcp --> db
  mcp -->|compact only| model
```

The supervisor page starts the Nimble wrapper. The wrapper registers the session, then searches and appends each result. The page lists that session, shows its timeline, compacts it, and can terminate it. LFM2.5 runs only on compact. Both clients store through the same MCP server.

---

Long Horizon Agents Hackathon
San Francisco
September 25, 2026.