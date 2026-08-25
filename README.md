# Agent Farm

Agent Farm is a controlled experiment in emergent website development. Every turn, one local Ollama model receives the inherited static site through OpenCode and the instruction:

> Build a website humans would want to visit.

The model may preserve, redesign, or replace the site. Only candidates that pass deterministic static and browser validation enter the public lineage.

## Safety model

- OpenCode sees a copied website, not this repository or its Git history.
- Participating models receive no credentials, external network, personas, handoffs, or prior logs.
- The runner can reach host Ollama only through loopback.
- A separate publisher owns a repository-scoped deploy key and revalidates candidates before pushing.
- GitHub Pages deploys only `site/`.
- Failed attempts are kept locally for 90 days; compact records are pushed to the orphan `observations` branch.

## Local setup

```bash
./scripts/bootstrap-runtime.sh
.venv/bin/python -m agent_lab.cli preflight
```

The bootstrap creates `.venv`, installs a pinned project-local Node/OpenCode runtime under `.runtime`, and downloads Playwright Chromium there. It does not alter global Python or Node installations.

After completing [GitHub setup](docs/github-setup.md):

```bash
./scripts/install-system-units.sh
.venv/bin/python -m agent_lab.cli run-once
.venv/bin/python -m agent_lab.cli publish
sudo .venv/bin/python -m agent_lab.cli resume
```

Use `status` and `prune` as your normal user; use `pause` and `resume` with `sudo` because they control system units. The services themselves run as `adminvince` from the isolated project runtime. The timer schedules a new turn 30 minutes after the previous runner exits and never intentionally overlaps work.
