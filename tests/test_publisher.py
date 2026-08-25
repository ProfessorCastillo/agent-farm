import json
import subprocess
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from agent_lab.config import PublishConfig, load_config
from agent_lab.publisher import _compact_record, publish_next
from agent_lab.state import atomic_write_json


class PublisherTests(TestCase):
    def test_compact_record_is_retry_stable(self) -> None:
        record = {
            "schema_version": 1,
            "run_id": "run-1",
            "started_at": "2026-08-25T00:00:00+00:00",
            "published_at": "2026-08-25T00:01:00+00:00",
            "accepted": False,
            "raw_archive": "/secret/local/path",
        }
        first = _compact_record(record, None)
        second = _compact_record(record, None)
        self.assertEqual(first, second)
        self.assertNotIn("raw_archive", first)

    def test_accepted_candidate_pushes_main_and_observations(self) -> None:
        source_config = load_config(Path("lab/config.toml"))
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            seed = root / "seed"
            remote = root / "remote.git"
            state = root / "state"
            source_site = root / "source" / "site"
            seed.mkdir()
            source_site.mkdir(parents=True)
            subprocess.run(["git", "init", "-b", "main"], cwd=seed, check=True, capture_output=True)
            (seed / "site").mkdir()
            original = Path("site/index.html").read_text()
            (seed / "site" / "index.html").write_text(original)
            subprocess.run(["git", "add", "site"], cwd=seed, check=True)
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
                cwd=seed,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "clone", "--bare", str(seed), str(remote)],
                check=True,
                capture_output=True,
            )

            run_id = "20260825T000000Z-deadbeef"
            run_dir = state / "raw" / run_id
            candidate = run_dir / "candidate"
            spool = state / "spool"
            candidate.mkdir(parents=True)
            spool.mkdir(parents=True)
            changed = original.replace(
                "The experiment has not begun.",
                "The publisher integration test passed.",
            )
            (candidate / "index.html").write_text(changed)
            record = {
                "schema_version": 1,
                "run_id": run_id,
                "started_at": "2026-08-25T00:00:00+00:00",
                "finished_at": "2026-08-25T00:00:05+00:00",
                "model": "ollama/test",
                "pool_version": 1,
                "epoch": 1,
                "epoch_seed": 1,
                "epoch_position": 0,
                "opencode_version": "test",
                "duration_seconds": 5,
                "returncode": 0,
                "timed_out": False,
                "status": "accepted",
                "reason": None,
                "accepted": True,
                "changed_files": ["index.html"],
                "before_manifest": {},
                "after_manifest": {},
                "validation": {"ok": True},
                "final_output_excerpt": "done",
            }
            atomic_write_json(run_dir / "record.json", record)
            atomic_write_json(spool / f"{run_id}.json", record)
            key = root / "deploy-key"
            key.write_text("unused for a local remote")
            key.chmod(0o600)
            (source_site / "index.html").write_text(original)

            config = replace(
                source_config,
                repo=root / "source",
                site_dir=source_site,
                state_dir=state,
                publish=PublishConfig(
                    remote=str(remote),
                    main_branch="main",
                    deploy_key=key,
                ),
            )
            result = publish_next(config, browser=False)

            self.assertEqual(result["status"], "published")
            self.assertTrue(result["accepted"])
            self.assertFalse((spool / f"{run_id}.json").exists())
            refs = subprocess.run(
                ["git", "for-each-ref", "--format=%(refname)", "refs/heads"],
                cwd=remote,
                text=True,
                capture_output=True,
                check=True,
            ).stdout.splitlines()
            self.assertIn("refs/heads/main", refs)
            self.assertIn("refs/heads/observations", refs)
            published = subprocess.run(
                ["git", "show", "main:site/index.html"],
                cwd=remote,
                text=True,
                capture_output=True,
                check=True,
            ).stdout
            self.assertIn("publisher integration test passed", published)
