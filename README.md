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

## Recreate the environment

`src/.venv` is a local Python 3.12 environment for Apple Silicon. To build it again:

```bash
python3.12 -m venv src/.venv
src/.venv/bin/pip install -r src/requirements.txt
src/.venv/bin/pip install -r supervisor/requirements.txt
```
