# Next steps

The website-evolution lab is implemented and validated locally. Complete this checklist in order to preserve the pilot, authorize publication, verify host isolation, and then enable the half-hour schedule.

Current state:

- Local implementation commit: `00edb35`
- Local `main` is ahead of `origin/main`; nothing has been pushed
- GitHub Pages is not enabled
- The publisher deploy key exists locally but is not registered with GitHub
- The systemd units are not installed or enabled
- The writing pilot is preserved on `experiments/writing-pilot` and tagged `writing-pilot-2026-08-23`
- The local test suite has 13 passing tests, and the full preflight passed

## 1. Push the preserved pilot

Use your normal GitHub credentials to push the archive branch and annotated tag before changing remote `main`:

```bash
git push origin experiments/writing-pilot
git push origin writing-pilot-2026-08-23
```

Confirm both appear on GitHub before continuing. The pilot files removed from `main` remain recoverable from this branch and tag.

## 2. Push the lab baseline

Review the local state:

```bash
git status --short --branch
git log -1 --oneline
```

Then push without force:

```bash
git push origin main
```

If Git reports that remote `main` has moved, stop and reconcile the remote changes instead of force-pushing.

## 3. Give the publisher write access

Display the already-generated public key:

```bash
sed -n '1p' .secrets/github-pages-deploy-key.pub
```

In the GitHub repository:

1. Open **Settings → Deploy keys → Add deploy key**.
2. Set the title to `agent-farm publisher`.
3. Paste the public key.
4. Select **Allow write access**.
5. Save the key.

Expected fingerprint:

```text
SHA256:3GARRHylL8AoUikyo5A6F1Zi66mpuU7ipg/LnIlu21s
```

Never upload, copy, or commit `.secrets/github-pages-deploy-key`, which is the private key. OpenCode cannot read `.secrets`; only the separate publisher service receives this credential.

Test the registered key:

```bash
ssh -T -i .secrets/github-pages-deploy-key \
  -o IdentitiesOnly=yes \
  git@github.com
```

GitHub should identify the repository and say that shell access is unavailable. The command can return a nonzero status because GitHub does not provide interactive SSH shells.

The repository currently has no repository rulesets. Keep direct deploy-key pushes to `main` available. A future rule requiring pull requests or blocking the deploy key will stop publication unless that key is explicitly allowed to bypass the rule.

## 4. Enable GitHub Actions and Pages

In **Settings → Actions → General**, ensure Actions is enabled and workflows using the official `actions/*` actions are permitted.

In **Settings → Pages**:

1. Find **Build and deployment**.
2. Set **Source** to **GitHub Actions**.

The committed workflow at `.github/workflows/pages.yml` uploads only `site/`. It does not need a repository secret: Pages uses GitHub's short-lived `GITHUB_TOKEN`. The deploy key is only for the headless publisher's Git pushes.

In **Actions → Deploy evolving site to GitHub Pages**, run the workflow once if the push did not already trigger it. Confirm that:

- The workflow succeeds.
- A `github-pages` environment is created.
- The public Pages URL loads the neutral placeholder.

## 5. Re-run local preflight

From the repository root:

```bash
.venv/bin/python -m agent_lab.cli preflight
```

Do not continue unless every preflight check passes, including the OpenCode runtime, all ten configured Ollama models, static validation, and browser validation.

## 6. Install the system services

Install and verify the system-level units:

```bash
./scripts/install-system-units.sh
```

The installer requires sudo. It installs the units but deliberately does not enable or start the timer. Although these are system units, the actual runner and publisher processes execute as the unprivileged `adminvince` user.

## 7. Prove runner network isolation

This is a mandatory activation gate. User-level systemd network filtering was tested on this host and did not block public network access, so the lab uses system-level units.

The first probe must succeed because Ollama is on host loopback:

```bash
sudo systemd-run --wait --pipe --collect \
  -p User=adminvince \
  -p IPAddressDeny=any \
  -p IPAddressAllow=localhost \
  /usr/bin/curl --fail --silent --show-error --output /dev/null --max-time 5 \
  http://127.0.0.1:11434/api/tags
```

The second probe must fail because GitHub is on the public internet:

```bash
sudo systemd-run --wait --pipe --collect \
  -p User=adminvince \
  -p IPAddressDeny=any \
  -p IPAddressAllow=localhost \
  /usr/bin/curl --fail --silent --show-error --output /dev/null --max-time 5 \
  https://github.com
```

Do not start the lab if the GitHub request succeeds. Inspect the host's systemd/cgroup network-filter support before proceeding.

## 8. Run one complete turn manually

Start one runner turn:

```bash
sudo systemctl start agent-farm-run.service
```

The publisher is connected through `OnSuccess=`, so it runs only after the runner produces an accepted candidate. Inspect both services:

```bash
sudo journalctl \
  -u agent-farm-run.service \
  -u agent-farm-publish.service \
  -n 200 \
  --no-pager
```

Before scheduling recurring turns, confirm all of the following:

- OpenCode selected one model from the frozen pool.
- The candidate made a material change and passed static and browser validation.
- The publisher revalidated the candidate.
- New commits appeared on both `main` and `observations`.
- The two refs were pushed atomically.
- The Pages workflow succeeded.
- The public site displays the accepted version.
- The observation record and screenshots exist under `.lab-state`.

If the turn fails, leave the timer disabled and diagnose the journals and `.lab-state` artifacts.

## 9. Enable the half-hour schedule

Only after the manual turn succeeds:

```bash
sudo .venv/bin/python -m agent_lab.cli resume
systemctl list-timers agent-farm-run.timer
```

The timer uses `OnUnitInactiveSec=30min`, so the next interval begins after the previous turn finishes rather than overlapping a slow run.

Check status at any time:

```bash
.venv/bin/python -m agent_lab.cli status
sudo systemctl status agent-farm-run.timer
```

## Emergency stop

Disable future scheduled turns:

```bash
sudo .venv/bin/python -m agent_lab.cli pause
```

This stops and disables the timer. Inspect any currently running service separately:

```bash
sudo systemctl status agent-farm-run.service agent-farm-publish.service
```

For design details and troubleshooting context, see [plan.md](plan.md), [README.md](README.md), and [docs/github-setup.md](docs/github-setup.md).
