# GitHub setup

The writing pilot is already preserved remotely on
`experiments/writing-pilot` and at tag `writing-pilot-2026-08-23`. Complete the
remaining repository setup before activating either systemd timer.

## 1. Create the dedicated deploy key

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

## 2. Push the lab code

Review the main-branch changes, commit them with your normal identity, and push:

```bash
git push origin main
```

Do not force-push. If remote `main` has moved, reconcile it before activating the lab.

## 3. Restrict GitHub Actions

In **Settings → Actions → General**:

1. Select **Allow ProfessorCastillo, and select non-ProfessorCastillo, actions
   and reusable workflows**.
2. Enable **Allow or block specified actions and reusable workflows**, then
   allow the four exact action references used by `.github/workflows/pages.yml`:

   ```text
   actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09,
   actions/configure-pages@983d7736d9b0ae728b81ab479565c72886d7745b,
   actions/upload-pages-artifact@7b1f4a764d45c48632c6b24a0339c27f5614fb0b,
   actions/deploy-pages@d6db90164ac5ed86f2b6aed7e0febac5b3c0c03e
   ```

3. Select **Require actions to be pinned to a full-length commit SHA**.
4. Select **Require approval for all external contributors** for fork pull
   request workflows.
5. Select **Read repository contents and packages permissions** as the default
   workflow permission.
6. Leave **Allow GitHub Actions to create and approve pull requests** unchecked.

The Pages workflow declares its narrowly scoped `pages: write` and
`id-token: write` permissions itself. See GitHub's documentation for
[selected action policies][actions-settings].

[actions-settings]: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository

## 4. Enable GitHub Pages

In **Settings → Actions → General**, ensure Actions is enabled and workflows using the official `actions/*` actions are allowed. Then, in **Settings → Pages**, set **Build and deployment → Source** to **GitHub Actions**. The committed `pages.yml` workflow uploads only `site/`.

Run the workflow once from **Actions → Deploy evolving site to GitHub Pages → Run workflow**, or change a file under `site/` and push. Confirm the deployment creates the `github-pages` environment and that the public URL loads the neutral placeholder.

No repository secret is required for Pages deployment: the workflow uses GitHub's short-lived `GITHUB_TOKEN` with `pages: write` and `id-token: write`. The deploy key is used only by the headless publisher to push validated commits.

## 5. Test before scheduling

```bash
.venv/bin/python -m agent_lab.cli preflight
ssh -T -i .secrets/github-pages-deploy-key -o IdentitiesOnly=yes git@github.com
./scripts/install-system-units.sh
./scripts/probe-system-isolation.sh
```

The isolation probe must show that the project seed is readable, the runner
cannot see the private home or deploy key, the publisher can see only its
repository key, host-loopback Ollama is reachable, and the public internet is
blocked. Do not start the lab if any check fails. User-level
units are not a substitute on this host because their IP filter did not enforce
the external-network denial.

Once the isolation probe passes, run one complete turn manually:

```bash
sudo systemctl start agent-farm-run.service
sudo journalctl -u agent-farm-run.service -u agent-farm-publish.service -n 200
```

Verify one complete run, its observation, its Git commit, and the Pages deployment. Only then enable recurring execution:

```bash
sudo .venv/bin/python -m agent_lab.cli resume
sudo systemctl list-timers agent-farm-run.timer agent-farm-publish.timer
```

The runner's first scheduled firing is 10 minutes after activation and later
firings are 30 minutes after the prior run becomes inactive. The five-minute
publication-retry timer is also enabled by `resume`; a pending publication
blocks the next model turn.

Emergency stop:

```bash
sudo .venv/bin/python -m agent_lab.cli pause
```
