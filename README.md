# Agent Farm

Agent Farm is a controlled experiment in emergent website development. Every turn, one local Ollama model receives the inherited static site through OpenCode and the instruction:

> Build a website humans would want to visit.

The model may preserve, redesign, or replace the site. Only candidates that pass deterministic static and browser validation enter the public lineage.

## Safety model

- OpenCode works in a disposable copy of the website, with shell access and
  out-of-stage file tools denied.
- Participating models receive no credentials, external network, personas, handoffs, or prior logs.
- The system runner hides the user's home directory and deploy key, mounts the
  required runtime, harness, config, and site seed read-only, exposes
  `.lab-state` writable, leaves `.git` and project documentation absent, and can
  reach host Ollama only through loopback.
- `.lab-state/lineage/site` is authoritative. It advances only after an accepted
  candidate is confirmed on the remote `main` branch, so every later turn
  inherits the last successfully published site.
- A separate publisher owns a repository-scoped deploy key and revalidates candidates before pushing.
- GitHub Pages deploys only `site/`.
- Failed attempts are kept locally for 90 days; strictly typed, aggregate-only
  records are pushed to the orphan `observations` branch. Raw model output,
  validation messages, filenames, and host paths remain local.
- An independent five-minute publisher timer retries a durable spool without
  consuming another model turn.

## Local setup

```bash
./scripts/bootstrap-runtime.sh
.venv/bin/python -m agent_lab.cli preflight
```

The bootstrap creates `.venv`, installs a pinned project-local Node/OpenCode runtime under `.runtime`, and downloads Playwright Chromium there. It does not alter global Python or Node installations.

After completing [GitHub setup](docs/github-setup.md):

```bash
./scripts/install-system-units.sh
./scripts/probe-system-isolation.sh
sudo systemctl start agent-farm-run.service
sudo .venv/bin/python -m agent_lab.cli resume
```

Use `status` and `prune` as your normal user; use `pause` and `resume` with `sudo` because they control system units. The services themselves run as `adminvince` from the isolated project runtime. The timer schedules a new turn 30 minutes after the previous runner exits and never intentionally overlaps work.

Direct `run-once` and `publish` CLI commands are retained for tests and
diagnostics. Production turns must be started through
`agent-farm-run.service`; invoking the CLI directly does not create the
systemd filesystem and network sandbox.
