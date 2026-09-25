# Horizon

Horizon is the server in the middle. The supervisor and the Nimble wrapper are the only two clients, and they call different tools.

```mermaid
flowchart LR
  subgraph clients [Two clients]
    sup["Supervisor page<br/>list, timeline, compact, terminate"]
    wrap["Agent wrapper<br/>register, append, read back"]
    search[Nimble search]
  end

  subgraph horizon [Horizon]
    mcp[MCP server on HTTP]
    db[RawTree]
    model[LFM2.5]
  end

  sup -->|list_agents, get_timeline, compact, terminate_agent| mcp
  sup -->|starts| wrap
  wrap -->|register_agent, append_event, get_timeline| mcp
  wrap -->|search| search
  mcp --> db
  mcp -->|compact only| model
```

The supervisor page starts the Nimble wrapper. The wrapper registers the session, then searches and appends each result. The page lists that session, shows its timeline, compacts it, and can terminate it. LFM2.5 runs only on compact. Both clients store through the same MCP server.

The shrink loop is a later read. `append_event` stores the raw event. Compact folds the visible prefix under the session goal, which is the launch sentence. The wrapper then calls `get_timeline` and continues from `working_state` plus events after `cutoff_seq`.

```mermaid
sequenceDiagram
  participant wrap as Nimble wrapper
  participant mcp as Horizon
  participant model as LFM2.5
  participant page as Supervisor page

  wrap->>mcp: append_event
  wrap->>mcp: get_timeline
  Note over wrap: working_state empty, suffix wheel continues
  page->>mcp: compact
  mcp->>model: goal plus visible events
  model-->>mcp: working_state
  wrap->>mcp: get_timeline
  mcp-->>wrap: goal, facts, open_questions, decisions, events after cutoff
  Note over wrap: next query is goal plus first open question
  Note over wrap: terminal prints that query
  wrap->>mcp: append_event
  Note over page: new event on top of the folded state
  Note over wrap: eight seconds later, repeat
```

`working_state` is `goal`, `facts`, `open_questions`, and `decisions`. Until Compact, that object is empty and the Nimble suffix wheel continues. After Compact, the next query is the launch sentence plus the first open question, the terminal prints it, and the page shows the new event on the folded state. The next Compact folds those new events, and the wrapper calls `get_timeline` again. The Nimble sample only registers and appends. It does not call `get_timeline`.

---

Long Horizon Agents Hackathon
San Francisco
September 25, 2026.