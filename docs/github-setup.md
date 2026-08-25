# GitHub setup

The repository is public at `ProfessorCastillo/agent-farm`, but GitHub Pages is not enabled yet. Complete these steps only after reviewing and pushing the initial lab commit.

## 1. Preserve and push the pilot

Push the local archive branch and annotated tag using your normal account credentials:

```bash
git push origin experiments/writing-pilot
git push origin writing-pilot-2026-08-23
```

Do this before replacing the remote `main` branch with the website-lab baseline.

## 2. Create the dedicated deploy key

Create a new key without a passphrase at the path expected by `lab/config.toml`:

```bash
mkdir -p .secrets
ssh-keygen -t ed25519 -C "agent-farm publisher" -f .secrets/github-pages-deploy-key
chmod 600 .secrets/github-pages-deploy-key
```

Do not commit either key file.

In GitHub:

1. Open **Settings → Deploy keys → Add deploy key**.
2. Name it `agent-farm publisher`.
3. Paste the contents of `.secrets/github-pages-deploy-key.pub`.
4. Select **Allow write access**.
5. Save it.

Keep direct pushes to `main` available to this key. The repository currently has no repository rulesets; a future rule that requires pull requests or otherwise blocks deploy-key pushes will stop publication unless the key is explicitly allowed to bypass it.

The private key is visible only to the publisher service. OpenCode runs without access to `.secrets`.

## 3. Push the lab baseline

Review the main-branch changes, commit them with your normal identity, and push:

```bash
git push origin main
```

Do not force-push. If remote `main` has moved, reconcile it before activating the lab.

## 4. Enable GitHub Pages

In **Settings → Actions → General**, ensure Actions is enabled and workflows using the official `actions/*` actions are allowed. Then, in **Settings → Pages**, set **Build and deployment → Source** to **GitHub Actions**. The committed `pages.yml` workflow uploads only `site/`.

Run the workflow once from **Actions → Deploy evolving site to GitHub Pages → Run workflow**, or change a file under `site/` and push. Confirm the deployment creates the `github-pages` environment and that the public URL loads the neutral placeholder.

No repository secret is required for Pages deployment: the workflow uses GitHub's short-lived `GITHUB_TOKEN` with `pages: write` and `id-token: write`. The deploy key is used only by the headless publisher to push validated commits.

## 5. Test before scheduling

```bash
.venv/bin/python -m agent_lab.cli preflight
ssh -T -i .secrets/github-pages-deploy-key -o IdentitiesOnly=yes git@github.com
./scripts/install-system-units.sh
```

Before starting the runner, prove that the system service's network filter behaves correctly on this host. The first command must succeed because it targets host loopback; the second command must fail because it targets the public internet:

```bash
sudo systemd-run --wait --pipe --collect \
  -p User=adminvince \
  -p IPAddressDeny=any \
  -p IPAddressAllow=localhost \
  /usr/bin/curl --fail --silent --show-error --output /dev/null --max-time 5 \
  http://127.0.0.1:11434/api/tags

sudo systemd-run --wait --pipe --collect \
  -p User=adminvince \
  -p IPAddressDeny=any \
  -p IPAddressAllow=localhost \
  /usr/bin/curl --fail --silent --show-error --output /dev/null --max-time 5 \
  https://github.com
```

Do not start the lab if the external request succeeds. User-manager units are not an acceptable substitute on this host: the same filter was tested under `systemd-run --user` and did not block external traffic.

Once the isolation probe passes, run one complete turn manually:

```bash
sudo systemctl start agent-farm-run.service
sudo journalctl -u agent-farm-run.service -u agent-farm-publish.service -n 200
```

Verify one complete run, its observation, its Git commit, and the Pages deployment. Only then enable recurring execution:

```bash
sudo .venv/bin/python -m agent_lab.cli resume
systemctl list-timers agent-farm-run.timer
```

Emergency stop:

```bash
sudo .venv/bin/python -m agent_lab.cli pause
```
