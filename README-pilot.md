# Agent Farm: two-turn pilot

This pilot gives a succession of independently sampled Ollama models the open-ended instruction:

> Write something people would want to read.

Each participant receives a unique randomly composed persona, inherits the current `workspace/`, makes its own project decision, changes at least one project file, and writes a new immutable numbered handoff for its successor.

The default is two sequential turns. Change `turns` in `pilot.json` or override it at runtime:

```bash
python3 agent_farm.py --turns 4
```

## Install

Copy `agent_farm.py` and `pilot.json` into the root of the `agent-farm` repository. No third-party Python packages are required. Ollama must be running at `127.0.0.1:11434`.

Preview a randomized schedule without calling a model:

```bash
python3 agent_farm.py --plan
```

Run the default two-turn pilot:

```bash
python3 agent_farm.py
```

The harness creates:

```text
workspace/             agent-controlled project files
workspace/handoffs/0001.md  first preserved handoff
workspace/handoffs/0002.md  second preserved handoff
logs/pilot-*.json     per-turn observational records
logs/pilot-summary.json
```

When run inside a Git repository, the harness commits `workspace/` and `logs/` after each turn. It refuses to commit when it finds pre-existing staged changes. It does not push unless invoked with `--push`.

Useful variants:

```bash
# Run without Git commits
python3 agent_farm.py --no-commit

# Run two turns, commit each, and push each commit
python3 agent_farm.py --turns 2 --push

# Make a run reproducible by setting random_seed in pilot.json
```

## Pilot boundaries

Participants receive five tools: list files, read a text file, write a text file, append to a text file, and submit a handoff. Every path is restricted to `workspace/`. The generic write tools cannot modify `workspace/handoffs/`; only the dedicated handoff tool can write the newly assigned numbered file. Participants have no shell, network, Git credential, or access to the harness itself.

The pilot runs turns back-to-back. Scheduling one turn every 30 minutes should be added only after this basic succession test completes successfully.
