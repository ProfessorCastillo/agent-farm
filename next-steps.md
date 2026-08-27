# Next steps — resume at GitHub Actions

You stopped at **Settings → Pages** with this message:

> Actions is currently unavailable for your repository.

That means repository Actions are disabled. Do not select either suggested
**Jekyll** or **Static HTML** workflow. The repository already has the custom
`.github/workflows/pages.yml` needed to deploy only `site/`.

The audit fixes are still local and uncommitted. Local verification currently
passes 66 tests, and no systemd units or timers have been activated.

## 1. Enable GitHub Actions now

Open **Settings → Actions → General**.

Under **Actions permissions**:

1. Select **Allow ProfessorCastillo, and select non-ProfessorCastillo, actions
   and reusable workflows**.
2. In the options that appear, select **Allow actions created by GitHub**.
3. Leave **Allow Marketplace actions by verified creators** unchecked.
4. Leave **Allow or block specified actions and reusable workflows** unchecked.
   The workflow uses only GitHub-owned `actions/*` actions, and every direct
   action reference is already pinned to a full commit SHA.
5. Select **Require actions to be pinned to a full-length commit SHA**.

Use these remaining settings:

- **Artifact and log retention:** 30 days.
- **Cache retention:** leave the default.
- **Fork pull request approval:** **Require approval for all external
  contributors**.
- **Workflow permissions:** **Read repository contents and packages
  permissions**.
- **Allow GitHub Actions to create and approve pull requests:** unchecked.

Scroll to the bottom and click **Save**. This save is the step that clears the
“Actions is currently unavailable” blocker. GitHub's reference for these
controls is [Managing GitHub Actions settings][actions-settings].

If the page will not save or still says Actions are disabled after a refresh,
check whether an account, organization, or enterprise policy is overriding the
repository. Do not proceed to scheduling the lab until Actions can run.

## 2. Return to Pages and deploy the existing workflow

Return to **Settings → Pages** and refresh the page.

1. Under **Build and deployment → Source**, select **GitHub Actions**.
2. Do not click **Configure** on either suggested workflow.
3. Open **Actions → Deploy evolving site to GitHub Pages**.
4. Click **Run workflow**, select branch **main**, and click the green
   **Run workflow** button.
5. Wait for the run to finish successfully.
6. Open <https://professorcastillo.github.io/agent-farm/> and confirm the current
   site loads.

The previous failed run reached `actions/configure-pages` before Pages was
available. Start a new manual run after enabling Actions rather than debugging
that old run. The audit-fix push in step 3 will not itself trigger Pages because
the workflow intentionally runs on changes to `site/**` or the workflow file,
not changes to the Python harness.

GitHub documents selecting an existing custom workflow under
[Configuring a publishing source][pages-source].

[actions-settings]: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository
[pages-source]: https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site

## 3. Review and publish the local audit fixes

```bash
git diff --check
.venv/bin/python -m unittest discover -s tests -v
git status --short --branch
```

Review the diff, commit it with your normal identity, and push without force:

```bash
git add agent_lab lab scripts tests README.md plan.md next-steps.md \
  docs/github-setup.md pyproject.toml
git commit -m "harden autonomous website lab"
git push origin main
```

If remote `main` moved, reconcile it rather than force-pushing. The preserved
pilot remains at `experiments/writing-pilot` and
`writing-pilot-2026-08-23`.

## 4. Register the publisher deploy key, if needed

Display only the public key:

```bash
sed -n '1p' .secrets/github-pages-deploy-key.pub
```

In **Settings → Deploy keys → Add deploy key**, use the title
`agent-farm publisher`, paste the public key, select **Allow write access**, and
save it. Never upload or commit `.secrets/github-pages-deploy-key`; that is the
private key.

Test the registered key:

```bash
ssh -T -i .secrets/github-pages-deploy-key \
  -o IdentitiesOnly=yes \
  git@github.com
```

GitHub can return a nonzero status after identifying the repository because it
does not provide an interactive shell. Repository rules must continue to permit
this deploy key to push directly to `main` and `observations`.

## 5. Run the application preflight

```bash
.venv/bin/python -m agent_lab.cli preflight
```

Do not continue unless every check passes: the inherited lineage, exact
OpenCode policy and version, all ten Ollama models, Ollama connectivity, deploy
key mode, static validation, and mandatory Playwright validation.

## 6. Install the four system units

```bash
./scripts/install-system-units.sh
```

The installer uses sudo, verifies the unit files, and deliberately does not
start or enable them. The units are system-level so the IP filter is enforceable,
but the processes run as unprivileged user `adminvince`.

## 7. Prove filesystem and network isolation

```bash
./scripts/probe-system-isolation.sh
```

This mandatory probe uses the service sandbox properties and verifies:

- the read-only project seed remains visible;
- the user's private home and publisher key are invisible;
- the publisher can read its repository key while unrelated home content stays hidden;
- OpenCode can read a staged canary but cannot read or leak a sibling state canary;
- host Ollama is reachable through `127.0.0.1:11434`;
- the public internet is blocked.

Do not start the lab if any check fails. The probe exercises the resolved
OpenCode denial policy as well as the systemd filesystem and network boundary.

## 8. Run one turn through the sandbox

Do not invoke `run-once` directly for a production turn. Start the system
service so the filesystem and network sandbox applies:

```bash
sudo systemctl start agent-farm-run.service
sudo journalctl \
  -u agent-farm-run.service \
  -u agent-farm-publish.service \
  -n 250 \
  --no-pager
```

Both successful and failed runner exits trigger the publisher. An accepted
candidate is revalidated, pushed atomically to `main` and `observations`, and
then installed as the authoritative lineage. A rejected/no-change/failed turn
updates only `observations`; its candidate never enters the lineage.

Before scheduling, verify:

- the runner selected one configured model and finalized exactly one turn;
- the publisher removed the corresponding spool entry only after remote push;
- the observation contains no raw model output, paths, filenames, or error text;
- if accepted, Pages displays the accepted commit and
  `.lab-state/lineage/site` matches it;
- if rejected, `main` and the lineage remain unchanged.

If publication fails, leave the runner timer disabled and retry safely with:

```bash
sudo systemctl start agent-farm-publish.service
```

The durable spool makes this retry consume no model turn.

## 9. Enable both schedules

Only after the manual gate passes:

```bash
sudo .venv/bin/python -m agent_lab.cli resume
sudo systemctl list-timers agent-farm-run.timer agent-farm-publish.timer
```

The first scheduled run waits 10 minutes after activation; later runs wait 30
minutes after the runner becomes inactive. The independent publisher timer
checks for pending work every five minutes. A pending spool prevents a new model
turn.

Check status:

```bash
.venv/bin/python -m agent_lab.cli status
sudo systemctl status agent-farm-run.timer agent-farm-publish.timer
```

## Emergency stop

```bash
sudo .venv/bin/python -m agent_lab.cli pause
sudo systemctl status agent-farm-run.service agent-farm-publish.service
```

`pause` disables both future timers; it does not kill an already running
service. Inspect or stop an active service explicitly if necessary.

For design context, see [plan.md](plan.md), [README.md](README.md), and
[docs/github-setup.md](docs/github-setup.md).
