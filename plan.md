# Autonomous Website Evolution Lab

## Summary

Build a persistent experiment in which one OpenCode agent runs at a time against the inherited static website, using a shuffled, versioned pool of ten local Ollama models. Each turn receives the minimal instruction “Build a website humans would want to visit” plus operational constraints, may replace the site entirely, and publishes only after deterministic validation.

Preserve the writing pilot on an archive branch and tag, then give `main` a clean website-lab starting point. GitHub Pages will publish only `site/`; experimental metadata remains outside the rendered site.

## Implementation

### Runtime and isolation

- Put Python orchestration and Playwright in a pinned `.venv`.
- Install a pinned Node 22 runtime, OpenCode 1.18.21, and Playwright Chromium under gitignored `.runtime/`; do not use global NVM packages at runtime.
- Use a separate gitignored automation checkout and state tree so scheduled work never touches the user’s working tree.
- Launch OpenCode with an ephemeral `HOME`, `--pure`, JSON output, trusted inline configuration, and the selected `ollama/<model>` identifier. OpenCode supports custom config through `OPENCODE_CONFIG_CONTENT` and local Ollama discovery. [OpenCode configuration](https://dev.opencode.ai/docs/config), [OpenCode providers](https://opencode.ai/docs/providers/)
- Allow native file inspection and editing only inside the staged website. Deny external directories, web tools, subagents, skills, questions, package installation, Git operations, and all shell commands. Run the service with `ProtectHome=tmpfs`; bind only the required virtual environment, runtime, harness, lab config, and site seed read-only; bind `.lab-state` writable; and leave `.git`, project documentation, and `.secrets` absent.
- Give the runner host-loopback access to Ollama but no external network by using `IPAddressDeny=any` with `IPAddressAllow=localhost`. Do not use `PrivateNetwork=yes`, because a private network namespace would hide Ollama on the host's `127.0.0.1:11434`. Verify the IP filter on this host during preflight and fail closed if it is unavailable. Keep the GitHub deploy key completely outside the runner's environment and filesystem view.

### Turn lifecycle

- Define model pool v1 explicitly as `ollama/gemma4:26b`, `ollama/gemma4:31b`, `ollama/gpt-oss:20b-131k`, `ollama/muse-glimmer:30b`, `ollama/nemotron-3-nano:30b`, `ollama/nemotron-3.5-lightning:30b`, `ollama/ornith-1.5:35b`, `ollama/qwen3.5:27b`, `ollama/qwen3.6:35b`, and `ollama/qwen3.8:27b`. Register `gemma4:31b` explicitly if OpenCode's automatic discovery continues to omit it; Ollama reports that it supports completion, vision, tools, and thinking.
- Shuffle models in persistent seeded epochs; consume every model once before reshuffling. Failures still count as turns and never cause automatic removal.
- Keep a pool version fixed for each complete epoch. Additions or removals may occur only at an epoch boundary and must create a new version recorded in every subsequent observation.
- Give each agent only the current website files—no Git history, personas, handoffs, prior logs, or experiment commentary.
- Prompt with the original instruction plus: inspect the inherited site, make a material change, keep it dependency-free and static, and finish within the turn.
- Run OpenCode for at most 30 minutes, capture its process group, and always unload the selected Ollama model afterward.
- Compare content manifests before and after. A candidate must change at least one permitted website file; metadata-only and whitespace-only changes fail.
- Allow wholesale redesigns and deletion of predecessor work, provided the resulting candidate remains valid.
- Every finalized turn enters a durable publisher spool so its compact outcome can be observed. Failed/no-change/timed-out candidates are archived but discarded from the lineage. A crash after reservation is automatically finalized as interrupted on the next invocation; a previously completed `record.json` is preserved and re-spooled rather than overwritten.
- Keep `.lab-state/lineage/site` as the authoritative inherited website. Seed it once from `site/`, and advance it only after the publisher confirms an accepted commit on remote `main`. Directory replacement is transactional and recoverable after interruption.

### Validation and publication

- Require `index.html`, regular files only, no symlinks or executable files, at most 500 files, a 50 MB total limit, and a 10 MB per-file limit.
- Permit dependency-free HTML, CSS, JavaScript, JSON, plain text, web manifests, fonts, and local raster assets. Reject SVG, XML, and media elements because they introduce active or insufficiently audited execution/resource surfaces. Forbid package manifests, OpenCode configuration, hidden agent instructions, server code, and harness files.
- Require this fixed CSP meta policy on every HTML page: `default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-src 'none'`. Inline CSS and JavaScript are deliberately supported because local models commonly produce single-file sites; omitting `'unsafe-eval'` continues to block `eval()` and `new Function()`.
- Deterministically reject forms/data collection, external scripts or runtime requests, redirects, downloads, cookies/storage, service workers, `eval`/dynamic code generation, obfuscated payloads, and known mining/phishing patterns. Do not judge aesthetics or editorial quality.
- Serve the candidate locally and use isolated Playwright Chromium to crawl up to 30 local pages, verify local links/assets, abort and record every cross-origin browser request, reject page or console errors, and save desktop and mobile screenshots. Bound each browser operation to 15 seconds and the entire browser phase to 120 seconds.
- Have a separate publisher service revalidate the result, replace `site/`, create an agent-attributed commit, and push with `git push --atomic`; never force-push.
- Publish GitHub Pages through a pinned Actions workflow that uploads only `site/`. The current repository has Pages disabled, so enable workflow-based Pages during bootstrap. Keep the site comfortably below GitHub’s 1 GB Pages limit. [GitHub Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)

### Git history and observations

- Create `experiments/writing-pilot` from the current `HEAD` in a temporary worktree, copy in and commit the currently untracked pilot harness, configurations, documentation, and archive material, and then create the annotated `writing-pilot-2026-08-23` tag from that complete snapshot. Push the archive branch and tag before cleaning `main`. Include the workspace and logs; exclude caches and duplicate ZIPs.
- Delete the untracked `.github/workflows/qwen-*.yml` files rather than archiving or committing them, because they are unrelated automation and include an hourly schedule. Add an exact ignore rule for those generated workflow names so only the intentional GitHub Pages workflow can be committed.
- Replace the pilot artifacts on `main` with the new harness, a neutral CSP-protected placeholder in `site/`, and the Pages workflow.
- Maintain an orphan `observations` branch containing compact permanent records, not raw OpenCode streams. Each record uses a strict typed schema containing identifiers, timestamps, model and epoch position, versions, duration, status, aggregate counts, tree hashes, validation counts, and the accepted main commit. Never publish model text, validation messages, filenames, local paths, screenshots, or raw tool output.
- Keep raw JSON events, stderr, candidate snapshot, failed patch, validation report, and screenshots locally for 90 days or until the archive reaches 25 GB, whichever requires pruning first.
- Push `main` and `observations` atomically for accepted turns; push only `observations` for rejected turns.

### systemd and credentials

- Install system-level `agent-farm-run.service`, `agent-farm-publish.service`, `agent-farm-run.timer`, and `agent-farm-publish.timer` that execute as the unprivileged `adminvince` user. User-level IP filtering was tested on this host and did not enforce `IPAddressDeny`, so the system manager is required for the runner's fail-closed cgroup/BPF network boundary.
- Schedule the first run 10 minutes after timer activation and later runs 30 minutes after the runner becomes inactive. Never overlap turns.
- If publication is pending or Git has diverged, do not start another agent. Retain the spool and retry publication every five minutes without consuming a model turn. Trigger the publisher after both successful and failed runner service exits as an additional prompt retry.
- Apply `NoNewPrivileges`, private temporary storage, a hidden home directory, a read-only host filesystem, explicit writable paths, `IPAddressDeny=any`, `IPAddressAllow=localhost`, `MemoryMax=12G`, `CPUQuota=300%`, low CPU/I/O priority, `TasksMax=256`, and a 45-minute service ceiling. Preflight must prove the configured model, termination, unload, browser, and bounded post-processing budgets fit beneath that ceiling. Explicitly omit `PrivateNetwork=yes`. Ollama remains a separately managed GPU service.
- Generate a new ED25519 write-enabled deploy key scoped solely to `ProfessorCastillo/agent-farm`, store it mode `0600`, and expose it only to the publisher. GitHub confirms deploy keys are repository-scoped and may be granted write access. [GitHub deploy keys](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys)
- Provide `preflight`, `run-once`, `publish`, `status`, `pause`, `resume`, and `prune` CLI commands. Browser validation is mandatory for production runs and publication; no static-only bypass exists. Treat direct `run-once` as a diagnostic entry point only because the systemd service supplies the host filesystem and network sandbox.

## Test Plan

- Unit-test epoch scheduling, state recovery, path confinement, manifest comparison, size/type limits, CSP rules, dangerous-code detection, record serialization, and retention pruning.
- Integration-test accepted changes, no-op turns, invalid HTML, broken links, external requests, timeout/process cleanup, model/API failure, OpenCode crash, failed Git push, retry, and remote divergence using fake OpenCode/Ollama and a local bare Git remote.
- Verify the exact OpenCode policy denies shell, external-directory, web, and delegation tools. Run the system-service isolation probe to confirm the private home and deploy key are invisible, the project is read-only except for state, host Ollama remains reachable at `127.0.0.1:11434`, and a request to an external address is denied.
- Run Playwright desktop/mobile smoke tests against representative valid and invalid sites.
- Validate units with `systemd-analyze`, manually execute one rejected and one accepted turn, confirm no overlap, then enable the timer.
- Confirm the archive branch/tag remotely, deploy the placeholder, verify the public Pages URL, run one real model turn, and confirm the public site matches the accepted commit while raw telemetry remains unpublished.

## Assumptions

- The experiment remains public, non-commercial, dependency-free, and contains no user data collection.
- GitHub Pages shows only the evolving creation; there is no public lab dashboard.
- Technical and safety validity determine publication; no model or human judges whether a site is aesthetically desirable.
- Failed work never enters the inherited website, but its compact record is permanent and its full artifacts remain locally for the retention window.
- No global Python, Node, OpenCode, browser, or Git credential configuration is modified. The only host-level additions are the four dedicated system units and the repository-scoped deploy key.
