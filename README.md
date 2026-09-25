# luma-long-horizon-agents

Luma Hackathon, September 25, 2026. Horizon keeps a long-running Nimble search session: the supervisor lists it, shows the timeline, folds older events into a working state, and can terminate the session.

## Run

From this directory, start Horizon and the supervisor in two terminals.

```bash
src/.venv/bin/python src/server.py --http
```

```bash
src/.venv/bin/python supervisor/app.py
```

Open http://127.0.0.1:8780. Horizon listens at http://127.0.0.1:8765/mcp.

Copy the template and fill in your keys before starting either process. `src/config.json` stays local.

```bash
cp src/config.example.json src/config.json
```

`rawtree_api_key` is the RawTree key. `nimble_api_key` is the Nimble key.

## Using the page

Type an instruction that contains `search`, `nimble`, or `nimbel`. The whole sentence becomes the session goal, and Launch starts a Nimble search that keeps running. Select the session to watch new events. Compact folds the visible prefix into a working state with a local LFM2.5 model. Terminate stops that process and drops the session from the list.

## Add an agent wrapper

Horizon manages a session after a wrapper registers it and appends events over MCP at http://127.0.0.1:8765/mcp. The wrapper is a long-running process and does not write to RawTree itself. `nimble_session/session.py` is the wrapper the page knows how to launch. A new wrapper uses the same calls.

1. Call `register_agent` with `name` and `goal`. Keep the returned `agent_id`. The `goal` is the launch sentence. Liquid keeps that goal and folds events under it.
2. Print `registered <agent_id>` on stdout. Terminate uses that line to stop a process the supervisor started.
3. Call `append_event` as the work proceeds. `kind` is `observation`, `action`, `decision`, or `artifact`. `summary` is the timeline line. `body` is the text Compact folds into the working state. That call stores the raw event. It does not return the folded state.
4. Exit when `append_event` reports that the session is terminated.

The page then lists the session, shows its timeline, and can compact or terminate it. Compact and terminate stay on the supervisor. Launch on the page starts only the Nimble wrapper. Run any other wrapper yourself against the same Horizon URL, then Refresh.

## Read the compacted state back

This is how the wrapper shrinks. After Compact runs, the wrapper calls `get_timeline` with its `agent_id`. The reply is the reduced footprint:

- `working_state` is the folded prefix: `goal`, `facts`, `open_questions`, and `decisions`. The launch sentence is the `goal` in that object.
- `events` holds only what was appended after that fold, where `seq` is greater than `cutoff_seq`.

The wrapper drops the history it already sent and continues from those two fields. The next `append_event` calls sit on top of that working state. The next Compact folds them in again, and the wrapper calls `get_timeline` once more.

`get_timeline` is implemented on Horizon. The supervisor page already uses it to draw the timeline. `nimble_session/session.py` does not call it, so that search loop does not read the folded state back.

In that Nimble loop, the read goes after every `append_event`. Until Compact is clicked, `working_state` is empty and the suffix wheel continues: the goal, then the goal plus `reliability over long tasks`, `what state should persist`, or `recent developments`. After Compact, the next search is the launch sentence plus the first `open_questions` entry, instead of the next suffix. The terminal prints that new query. The page shows the new event on top of the folded state. Eight seconds later the loop does it again.

## Recreate the environment

`src/.venv` is a local Python 3.12 environment for Apple Silicon. To build it again:

```bash
python3.12 -m venv src/.venv
src/.venv/bin/pip install -r src/requirements.txt
src/.venv/bin/pip install -r supervisor/requirements.txt
```
