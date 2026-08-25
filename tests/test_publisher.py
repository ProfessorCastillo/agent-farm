import json
import shlex
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from agent_lab.config import PublishConfig, load_config
from agent_lab import publisher as publisher_module
from agent_lab.lineage import ensure_lineage
from agent_lab.publisher import _compact_record, _git_env, publish_next
from agent_lab.state import atomic_write_json
from agent_lab.validation import content_manifest


class CompactRecordTests(TestCase):
    def test_compact_record_is_retry_stable_and_contains_no_free_form_text(self) -> None:
        secret = "/home/adminvince/.ssh/id_ed25519 PRIVATE MATERIAL"
        secret_filename = "ghp_" + "z" * 36 + ".html"
        digest = "a" * 64
        record = {
            "schema_version": 1,
            "run_id": "20260825T000000Z-deadbeef",
            "started_at": "2026-08-25T00:00:00+00:00",
            "finished_at": "2026-08-25T00:00:05+00:00",
            "published_at": "2026-08-25T00:01:00+00:00",
            "model": "ollama/test",
            "pool_version": 1,
            "epoch": 2,
            "epoch_seed": 3,
            "epoch_position": 4,
            "opencode_version": "1.18.21",
            "duration_seconds": 5.5,
            "returncode": 0,
            "timed_out": False,
            "status": "accepted",
            "reason": secret,
            "accepted": True,
            "changed_files": [secret, "index.html"],
            "before_manifest": {secret_filename: {"sha256": digest, "bytes": 12}},
            "after_manifest": {secret_filename: {"sha256": digest, "bytes": 12}},
            "validation": {
                "ok": False,
                "static_errors": [secret],
                "browser_errors": [f"console error: {secret}"],
                "checked_files": 1,
                "checked_pages": 2,
                "total_bytes": 12,
                "screenshots": [secret],
                "console": secret,
            },
            "final_output_excerpt": secret,
            "raw_archive": secret,
        }

        first = _compact_record(
            record,
            "b" * 40,
            expected_opencode_version="1.18.21",
        )
        second = _compact_record(
            record,
            "b" * 40,
            expected_opencode_version="1.18.21",
        )

        self.assertEqual(first, second)
        self.assertNotIn(secret, json.dumps(first))
        self.assertNotIn("reason", first)
        self.assertNotIn("final_output_excerpt", first)
        self.assertNotIn("raw_archive", first)
        self.assertNotIn("changed_files", first)
        self.assertNotIn(secret_filename, json.dumps(first))
        self.assertEqual(first["changed_file_count"], 2)
        self.assertEqual(first["schema_version"], 2)
        self.assertEqual(first["opencode_version"], "1.18.21")
        self.assertNotIn("before_manifest", first)
        self.assertNotIn("after_manifest", first)
        self.assertEqual(first["before"]["file_count"], 1)
        self.assertEqual(first["before"]["total_bytes"], 12)
        self.assertRegex(first["before"]["tree_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(first["before"], first["after"])
        self.assertEqual(
            first["validation"],
            {
                "ok": False,
                "checked_files": 1,
                "checked_pages": 2,
                "total_bytes": 12,
                "static_error_count": 1,
                "browser_error_count": 1,
                "screenshot_count": 1,
            },
        )

        record["opencode_version"] = "ghp_" + "q" * 36
        poisoned = _compact_record(
            record,
            "b" * 40,
            expected_opencode_version="1.18.21",
        )
        self.assertIsNone(poisoned["opencode_version"])
        self.assertNotIn("ghp_", json.dumps(poisoned))

    def test_git_ssh_command_quotes_key_and_known_hosts_paths(self) -> None:
        key = Path("/tmp/key path;not-a-command")
        known_hosts = Path("/tmp/known hosts;also-not-a-command")

        command = shlex.split(_git_env(key, known_hosts)["GIT_SSH_COMMAND"])

        self.assertEqual(command[command.index("-i") + 1], str(key))
        self.assertIn(f"UserKnownHostsFile={known_hosts}", command)


class PublisherIntegrationTests(TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.seed = self.root / "seed"
        self.remote = self.root / "remote.git"
        self.state = self.root / "state"
        self.source_site = self.root / "source" / "site"
        self.seed.mkdir()
        self.source_site.mkdir(parents=True)
        subprocess.run(
            ["git", "init", "-b", "main"],
            cwd=self.seed,
            check=True,
            capture_output=True,
        )
        (self.seed / "site").mkdir()
        self.original = Path("site/index.html").read_text(encoding="utf-8")
        (self.seed / "site" / "index.html").write_text(
            self.original,
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "site"], cwd=self.seed, check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "-m",
                "seed",
            ],
            cwd=self.seed,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "clone", "--bare", str(self.seed), str(self.remote)],
            check=True,
            capture_output=True,
        )
        (self.source_site / "index.html").write_text(self.original, encoding="utf-8")
        self.key = self.root / "deploy-key"
        self.key.write_text("unused for a local remote", encoding="utf-8")
        self.key.chmod(0o600)
        source_config = load_config(Path("lab/config.toml"))
        self.config = replace(
            source_config,
            repo=self.root / "source",
            site_dir=self.source_site,
            state_dir=self.state,
            models=("ollama/test",),
            validation=replace(source_config.validation, require_browser=False),
            publish=PublishConfig(
                remote=str(self.remote),
                main_branch="main",
                deploy_key=self.key,
            ),
        )
        self.sequence = 0
        self.external_sequence = 0

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _queue(
        self,
        *,
        accepted: bool,
        content: str | None = None,
        secret_text: str | None = None,
    ) -> tuple[str, Path, Path]:
        self.sequence += 1
        run_id = f"20260825T0000{self.sequence:02}Z-deadbeef"
        run_dir = self.state / "raw" / run_id
        candidate = run_dir / "candidate"
        spool = self.state / "spool"
        candidate.mkdir(parents=True)
        spool.mkdir(parents=True, exist_ok=True)
        candidate_content = content if content is not None else self.original
        (candidate / "index.html").write_text(candidate_content, encoding="utf-8")
        validation = {
            "ok": accepted,
            "static_errors": [] if accepted else [secret_text or "rejected"],
            "browser_errors": [],
            "checked_files": 1,
            "checked_pages": 1 if accepted else 0,
            "total_bytes": len(candidate_content.encode()),
            "screenshots": ["desktop.png", "mobile.png"] if accepted else [],
        }
        record = {
            "schema_version": 1,
            "run_id": run_id,
            "started_at": f"2026-08-25T00:00:{self.sequence:02}+00:00",
            "finished_at": f"2026-08-25T00:00:{self.sequence + 1:02}+00:00",
            "model": "ollama/test",
            "pool_version": 1,
            "epoch": 1,
            "epoch_seed": 1,
            "epoch_position": self.sequence - 1,
            "opencode_version": "test",
            "duration_seconds": 5,
            "returncode": 0,
            "timed_out": False,
            "status": "accepted" if accepted else "rejected",
            "reason": secret_text if not accepted else None,
            "accepted": accepted,
            "changed_files": ["index.html"],
            "before_manifest": content_manifest(self.source_site),
            "after_manifest": content_manifest(candidate),
            "validation": validation,
            "final_output_excerpt": secret_text or "done",
        }
        atomic_write_json(run_dir / "record.json", record)
        spool_path = spool / f"{run_id}.json"
        atomic_write_json(spool_path, record)
        return run_id, candidate, spool_path

    def _remote_head(self, branch: str) -> str:
        return subprocess.run(
            ["git", "rev-parse", branch],
            cwd=self.remote,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()

    def _remote_show(self, ref_path: str) -> str:
        return subprocess.run(
            ["git", "show", ref_path],
            cwd=self.remote,
            text=True,
            capture_output=True,
            check=True,
        ).stdout

    def _external_commit(
        self,
        files: dict[str, str],
        *,
        branch: str = "main",
        message: str = "external update",
    ) -> str:
        self.external_sequence += 1
        checkout = self.root / f"external-{self.external_sequence}"
        subprocess.run(
            ["git", "clone", "--branch", branch, str(self.remote), str(checkout)],
            check=True,
            capture_output=True,
        )
        for relative, content in files.items():
            path = checkout / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=checkout, check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=External Test",
                "-c",
                "user.email=external@example.invalid",
                "commit",
                "-m",
                message,
            ],
            cwd=checkout,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "push", "origin", branch],
            cwd=checkout,
            check=True,
            capture_output=True,
        )
        return self._remote_head(branch)

    def _local_commit(
        self,
        checkout: Path,
        files: dict[str, str],
        *,
        message: str,
    ) -> str:
        for relative, content in files.items():
            path = checkout / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=checkout, check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Unexpected Test",
                "-c",
                "user.email=unexpected@example.invalid",
                "commit",
                "-m",
                message,
            ],
            cwd=checkout,
            check=True,
            capture_output=True,
        )
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=checkout,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()

    @patch("agent_lab.publisher.update_lineage")
    def test_accepted_candidate_pushes_main_and_observations(self, lineage) -> None:
        changed = self.original.replace(
            "The experiment has not begun.",
            "The publisher integration test passed.",
        )
        run_id, _, spool_path = self._queue(accepted=True, content=changed)

        result = publish_next(self.config, browser=False)

        self.assertEqual(result["status"], "published")
        self.assertTrue(result["accepted"])
        self.assertIsNotNone(result["main_commit"])
        self.assertFalse(spool_path.exists())
        lineage.assert_called_once_with(
            self.config,
            self.state / "repository" / "site",
        )
        published = self._remote_show("main:site/index.html")
        self.assertIn("publisher integration test passed", published)
        observation = json.loads(
            self._remote_show(f"observations:runs/2026/08/{run_id}.json")
        )
        self.assertEqual(observation["main_commit"], result["main_commit"])

    def test_successful_push_updates_authoritative_lineage_from_checkout(self) -> None:
        changed = self.original.replace(
            "The experiment has not begun.",
            "The real lineage integration test passed.",
        )
        self._queue(accepted=True, content=changed)

        result = publish_next(self.config, browser=False)

        lineage = ensure_lineage(self.config)
        lineage_text = (lineage / "index.html").read_text(encoding="utf-8")
        checkout_text = (
            self.state / "repository" / "site" / "index.html"
        ).read_text(encoding="utf-8")
        self.assertTrue(result["accepted"])
        self.assertIn("real lineage integration test passed", lineage_text)
        self.assertEqual(lineage_text, checkout_text)
        self.assertEqual(lineage_text, self._remote_show("main:site/index.html"))

    @patch("agent_lab.publisher.update_lineage")
    def test_candidate_mutation_between_validation_and_copy_is_not_pushed(
        self,
        lineage,
    ) -> None:
        changed = self.original.replace(
            "The experiment has not begun.",
            "The validated candidate must be the committed candidate.",
        )
        _, candidate, spool_path = self._queue(accepted=True, content=changed)
        real_replace_site = publisher_module._replace_site

        def mutate_then_copy(checkout, source, site_name):
            index = source / "index.html"
            index.write_text(
                index.read_text(encoding="utf-8").replace(
                    "The validated candidate must be the committed candidate.",
                    "This mutation was never validated.",
                ),
                encoding="utf-8",
            )
            real_replace_site(checkout, source, site_name)

        with patch(
            "agent_lab.publisher._replace_site",
            side_effect=mutate_then_copy,
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "copied site does not match the validated candidate",
            ):
                publish_next(self.config, browser=False)

        self.assertTrue(spool_path.exists())
        self.assertEqual(self._remote_show("main:site/index.html"), self.original)
        lineage.assert_not_called()

        (candidate / "index.html").write_text(changed, encoding="utf-8")
        result = publish_next(self.config, browser=False)

        self.assertEqual(result["status"], "published")
        self.assertFalse(spool_path.exists())
        self.assertEqual(self._remote_show("main:site/index.html"), changed)
        lineage.assert_called_once()

    @patch("agent_lab.publisher.update_lineage")
    def test_remote_advance_between_push_and_confirmation_is_allowed(self, lineage) -> None:
        changed = self.original.replace(
            "The experiment has not begun.",
            "Ancestor confirmation test.",
        )
        self._queue(accepted=True, content=changed)
        real_confirm = publisher_module._confirm_publication
        external_head: list[str] = []

        def advance_then_confirm(*args, **kwargs):
            if not external_head:
                external_head.append(
                    self._external_commit(
                        {"README.md": "# Concurrent external commit\n"},
                        message="advance during confirmation",
                    )
                )
            return real_confirm(*args, **kwargs)

        with patch(
            "agent_lab.publisher._confirm_publication",
            side_effect=advance_then_confirm,
        ):
            result = publish_next(self.config, browser=False)

        self.assertIsNotNone(result["main_commit"])
        self.assertNotEqual(result["main_commit"], external_head[0])
        self.assertEqual(self._remote_head("main"), external_head[0])
        lineage.assert_called_once_with(
            self.config,
            self.state / "repository" / "site",
        )

    @patch("agent_lab.publisher.update_lineage")
    def test_duplicate_candidate_does_not_attribute_unrelated_head(self, lineage) -> None:
        changed = self.original.replace(
            "The experiment has not begun.",
            "A duplicate candidate test.",
        )
        self._queue(accepted=True, content=changed)
        first = publish_next(self.config, browser=False)
        first_head = self._remote_head("main")
        second_run, _, _ = self._queue(accepted=True, content=changed)

        second = publish_next(self.config, browser=False)

        self.assertIsNotNone(first["main_commit"])
        self.assertIsNone(second["main_commit"])
        self.assertEqual(self._remote_head("main"), first_head)
        observation = json.loads(
            self._remote_show(f"observations:runs/2026/08/{second_run}.json")
        )
        self.assertIsNone(observation["main_commit"])
        self.assertEqual(lineage.call_count, 2)

    @patch("agent_lab.publisher.update_lineage")
    def test_failed_atomic_push_retains_spool_and_retries_existing_commits(
        self,
        lineage,
    ) -> None:
        changed = self.original.replace(
            "The experiment has not begun.",
            "Push retry test.",
        )
        run_id, _, spool_path = self._queue(accepted=True, content=changed)
        hook = self.remote / "hooks" / "pre-receive"
        hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        hook.chmod(0o700)

        with self.assertRaises(subprocess.CalledProcessError):
            publish_next(self.config, browser=False)

        self.assertTrue(spool_path.exists())
        lineage.assert_not_called()
        hook.unlink()
        result = publish_next(self.config, browser=False)

        self.assertFalse(spool_path.exists())
        self.assertIsNotNone(result["main_commit"])
        lineage.assert_called_once_with(
            self.config,
            self.state / "repository" / "site",
        )
        subjects = subprocess.run(
            ["git", "log", "--format=%s", "main"],
            cwd=self.remote,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.splitlines()
        self.assertEqual(
            subjects.count(f"website turn {run_id}: ollama/test"),
            1,
        )

    @patch("agent_lab.publisher.update_lineage")
    def test_local_commit_after_receipt_is_not_pushed(self, lineage) -> None:
        changed = self.original.replace(
            "The experiment has not begun.",
            "Post-receipt race test.",
        )
        _, _, spool_path = self._queue(accepted=True, content=changed)
        real_atomic_write_json = publisher_module.atomic_write_json
        injected = False

        def inject_after_receipt(path, value):
            nonlocal injected
            real_atomic_write_json(path, value)
            if (
                path == spool_path
                and isinstance(value, dict)
                and "_publication" in value
                and not injected
            ):
                injected = True
                self._local_commit(
                    self.state / "repository",
                    {"leak-after-receipt.txt": "must not be pushed"},
                    message="unowned post-receipt commit",
                )

        with patch(
            "agent_lab.publisher.atomic_write_json",
            side_effect=inject_after_receipt,
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "main branch changed after publication preparation",
            ):
                publish_next(self.config, browser=False)

        self.assertTrue(injected)
        self.assertTrue(spool_path.exists())
        leaked = subprocess.run(
            ["git", "cat-file", "-e", "main:leak-after-receipt.txt"],
            cwd=self.remote,
            capture_output=True,
        )
        self.assertNotEqual(leaked.returncode, 0)
        self.assertEqual(self._remote_show("main:site/index.html"), self.original)
        lineage.assert_not_called()

    def test_lineage_failure_after_push_retains_spool_for_idempotent_retry(self) -> None:
        changed = self.original.replace(
            "The experiment has not begun.",
            "Lineage retry test.",
        )
        run_id, _, spool_path = self._queue(accepted=True, content=changed)

        with patch(
            "agent_lab.publisher.update_lineage",
            side_effect=RuntimeError("simulated lineage failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "simulated lineage failure"):
                publish_next(self.config, browser=False)

        pushed_head = self._remote_head("main")
        self.assertTrue(spool_path.exists())
        receipt = json.loads(spool_path.read_text(encoding="utf-8"))["_publication"]
        self.assertEqual(receipt["main_commit"], pushed_head)
        external_head = self._external_commit(
            {"README.md": "# Unrelated external change\n"},
            message="advance main after atomic publication",
        )
        with patch("agent_lab.publisher.update_lineage") as lineage:
            result = publish_next(self.config, browser=False)

        self.assertFalse(spool_path.exists())
        self.assertEqual(result["main_commit"], pushed_head)
        self.assertEqual(self._remote_head("main"), external_head)
        lineage.assert_called_once_with(
            self.config,
            self.state / "repository" / "site",
        )
        final_record = json.loads(
            (self.state / "raw" / run_id / "record.json").read_text(encoding="utf-8")
        )
        self.assertNotIn("_publication", final_record)
        subjects = subprocess.run(
            ["git", "log", "--format=%s", "main"],
            cwd=self.remote,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.splitlines()
        self.assertEqual(
            subjects.count(f"website turn {run_id}: ollama/test"),
            1,
        )

    def test_remote_site_divergence_retains_confirmed_receipt(self) -> None:
        changed = self.original.replace(
            "The experiment has not begun.",
            "Candidate that reached the remote.",
        )
        _, _, spool_path = self._queue(accepted=True, content=changed)
        with patch(
            "agent_lab.publisher.update_lineage",
            side_effect=RuntimeError("simulated lineage failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "simulated lineage failure"):
                publish_next(self.config, browser=False)

        self._external_commit(
            {"site/index.html": self.original},
            message="replace the published site externally",
        )
        with patch("agent_lab.publisher.update_lineage") as lineage:
            with self.assertRaisesRegex(
                RuntimeError,
                "current remote site no longer matches",
            ):
                publish_next(self.config, browser=False)

        self.assertTrue(spool_path.exists())
        self.assertIn(
            "_publication",
            json.loads(spool_path.read_text(encoding="utf-8")),
        )
        lineage.assert_not_called()

    @patch("agent_lab.publisher.update_lineage")
    def test_unowned_ahead_main_commit_is_quarantined_not_pushed(self, lineage) -> None:
        first_content = self.original.replace(
            "The experiment has not begun.",
            "Initial accepted site.",
        )
        self._queue(accepted=True, content=first_content)
        publish_next(self.config, browser=False)
        checkout = self.state / "repository"
        self._local_commit(
            checkout,
            {"leak.txt": "must remain local"},
            message="unowned clean commit",
        )
        self._queue(accepted=False, secret_text="expected rejection")

        publish_next(self.config, browser=False)

        leaked = subprocess.run(
            ["git", "cat-file", "-e", "main:leak.txt"],
            cwd=self.remote,
            capture_output=True,
        )
        self.assertNotEqual(leaked.returncode, 0)
        quarantines = list(self.state.glob("repository.quarantine*"))
        self.assertTrue(any((path / "leak.txt").is_file() for path in quarantines))
        self.assertEqual(lineage.call_count, 1)

    @patch("agent_lab.publisher.update_lineage")
    def test_unowned_ahead_observation_commit_is_quarantined_not_pushed(
        self,
        lineage,
    ) -> None:
        self._queue(accepted=False, secret_text="first rejection")
        publish_next(self.config, browser=False)
        observations = self.state / "observations-worktree"
        self._local_commit(
            observations,
            {"leak.json": '{"secret": true}\n'},
            message="unowned observation commit",
        )
        self._queue(accepted=False, secret_text="second rejection")

        publish_next(self.config, browser=False)

        leaked = subprocess.run(
            ["git", "cat-file", "-e", "observations:leak.json"],
            cwd=self.remote,
            capture_output=True,
        )
        self.assertNotEqual(leaked.returncode, 0)
        quarantines = list(self.state.glob("observations-worktree.quarantine*"))
        self.assertTrue(any((path / "leak.json").is_file() for path in quarantines))
        lineage.assert_not_called()

    @patch("agent_lab.publisher.update_lineage")
    def test_locked_main_checkout_is_preserved_and_rebuilt(self, lineage) -> None:
        self._queue(accepted=False, secret_text="first rejection")
        publish_next(self.config, browser=False)
        lock = self.state / "repository" / ".git" / "index.lock"
        lock.write_text("stale lock", encoding="utf-8")
        self._queue(accepted=False, secret_text="second rejection")

        publish_next(self.config, browser=False)

        quarantines = list(self.state.glob("repository.quarantine*"))
        self.assertTrue(any((path / ".git" / "index.lock").is_file() for path in quarantines))
        self.assertFalse((self.state / "repository" / ".git" / "index.lock").exists())
        lineage.assert_not_called()

    @patch("agent_lab.publisher.update_lineage")
    def test_wrong_origin_checkout_is_preserved_and_recloned(self, lineage) -> None:
        first_content = self.original.replace(
            "The experiment has not begun.",
            "First remote only.",
        )
        self._queue(accepted=True, content=first_content)
        publish_next(self.config, browser=False)
        second_remote = self.root / "second-remote.git"
        subprocess.run(
            ["git", "clone", "--bare", str(self.seed), str(second_remote)],
            check=True,
            capture_output=True,
        )
        second_config = replace(
            self.config,
            publish=PublishConfig(
                remote=str(second_remote),
                main_branch="main",
                deploy_key=self.key,
            ),
        )
        second_content = self.original.replace(
            "The experiment has not begun.",
            "Second remote receives this turn.",
        )
        self._queue(accepted=True, content=second_content)

        publish_next(second_config, browser=False)

        first_published = self._remote_show("main:site/index.html")
        second_published = subprocess.run(
            ["git", "show", "main:site/index.html"],
            cwd=second_remote,
            text=True,
            capture_output=True,
            check=True,
        ).stdout
        self.assertIn("First remote only", first_published)
        self.assertIn("Second remote receives this turn", second_published)
        quarantines = list(self.state.glob("repository.quarantine*"))
        self.assertGreaterEqual(len(quarantines), 1)
        self.assertEqual(lineage.call_count, 2)

    @patch("agent_lab.publisher.update_lineage")
    def test_interrupted_unborn_observations_branch_is_recreated(self, lineage) -> None:
        _, _, spool_path = self._queue(
            accepted=False,
            secret_text="rejected turn",
        )
        real_git = publisher_module._git

        def interrupt_initial_commit(cwd, env, *args, **kwargs):
            if args[-3:] == ("commit", "-m", "initialize observations branch"):
                raise RuntimeError("simulated initialization interruption")
            return real_git(cwd, env, *args, **kwargs)

        with patch("agent_lab.publisher._git", side_effect=interrupt_initial_commit):
            with self.assertRaisesRegex(
                RuntimeError,
                "simulated initialization interruption",
            ):
                publish_next(self.config, browser=False)

        self.assertTrue(spool_path.exists())
        publish_next(self.config, browser=False)

        self.assertFalse(spool_path.exists())
        quarantines = list(self.state.glob("observations-worktree.quarantine*"))
        self.assertTrue(any((path / "README.md").is_file() for path in quarantines))
        self.assertTrue((self.state / "observations-worktree" / ".git").is_file())
        lineage.assert_not_called()

    @patch("agent_lab.publisher.update_lineage")
    def test_stale_observations_registration_is_pruned_and_path_quarantined(
        self,
        lineage,
    ) -> None:
        self._queue(accepted=False, secret_text="first rejection")
        publish_next(self.config, browser=False)
        observations = self.state / "observations-worktree"
        shutil.rmtree(observations)
        observations.mkdir()
        (observations / "preserve-me.txt").write_text("not automation data", encoding="utf-8")
        run_id, _, spool_path = self._queue(
            accepted=False,
            secret_text="host path must not be public",
        )

        result = publish_next(self.config, browser=False)

        self.assertEqual(result["status"], "published")
        self.assertFalse(spool_path.exists())
        self.assertTrue((observations / ".git").exists())
        quarantines = list(self.state.glob("observations-worktree.quarantine*"))
        self.assertEqual(len(quarantines), 1)
        self.assertEqual(
            (quarantines[0] / "preserve-me.txt").read_text(encoding="utf-8"),
            "not automation data",
        )
        public = self._remote_show(f"observations:runs/2026/08/{run_id}.json")
        self.assertNotIn("host path must not be public", public)
        lineage.assert_not_called()

    @patch("agent_lab.publisher.update_lineage")
    def test_dirty_publisher_owned_observation_is_recovered(self, lineage) -> None:
        self._queue(accepted=False, secret_text="first rejection")
        publish_next(self.config, browser=False)
        observations = self.state / "observations-worktree"
        partial = observations / "runs" / "2026" / "08" / "partial.json"
        partial.parent.mkdir(parents=True, exist_ok=True)
        partial.write_text('{"unfinished": true}\n', encoding="utf-8")
        subprocess.run(
            ["git", "add", "--", "runs"],
            cwd=observations,
            check=True,
            capture_output=True,
        )
        run_id, _, spool_path = self._queue(
            accepted=False,
            secret_text="second rejection",
        )

        result = publish_next(self.config, browser=False)

        self.assertEqual(result["status"], "published")
        self.assertFalse(spool_path.exists())
        self.assertFalse(partial.exists())
        remote_paths = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", "observations"],
            cwd=self.remote,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.splitlines()
        self.assertNotIn("runs/2026/08/partial.json", remote_paths)
        self.assertIn(f"runs/2026/08/{run_id}.json", remote_paths)
        lineage.assert_not_called()

    @patch("agent_lab.publisher.update_lineage")
    def test_dirty_publisher_owned_site_is_recovered(self, lineage) -> None:
        first_content = self.original.replace(
            "The experiment has not begun.",
            "First accepted site.",
        )
        self._queue(accepted=True, content=first_content)
        publish_next(self.config, browser=False)
        checkout = self.state / "repository"
        (checkout / "site" / "index.html").write_text(
            "partial publisher replacement",
            encoding="utf-8",
        )
        subprocess.run(
            ["git", "add", "--", "site"],
            cwd=checkout,
            check=True,
            capture_output=True,
        )
        second_content = self.original.replace(
            "The experiment has not begun.",
            "Second accepted site.",
        )
        self._queue(accepted=True, content=second_content)

        publish_next(self.config, browser=False)

        self.assertIn("Second accepted site", self._remote_show("main:site/index.html"))
        self.assertEqual(lineage.call_count, 2)
