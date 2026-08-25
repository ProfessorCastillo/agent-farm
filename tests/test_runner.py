import json
import shutil
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from agent_lab import runner as runner_module
from agent_lab.config import OpenCodeConfig, PublishConfig, load_config
from agent_lab.lineage import ensure_lineage, update_lineage
from agent_lab.runner import run_once
from agent_lab.state import SchedulerState, atomic_write_json
from agent_lab.validation import validate_static


class RunnerIntegrationTests(TestCase):
    def _fixture(self, root: Path):
        source_config = load_config(Path("lab/config.toml"))
        site = root / "site"
        state = root / ".lab-state"
        lab = root / "lab"
        runtime = root / ".runtime"
        site.mkdir()
        lab.mkdir()
        (lab / "systemd").mkdir()
        runtime.mkdir()
        (lab / "opencode.json").write_text("{}", encoding="utf-8")
        (lab / "systemd" / "agent-farm-run.service").write_text(
            "[Service]\nTimeoutStartSec=45min\n",
            encoding="utf-8",
        )
        initial = Path("site/index.html").read_text(encoding="utf-8")
        (site / "index.html").write_text(initial, encoding="utf-8")

        fake = runtime / "fake-opencode"
        fake.write_text(
            "#!/usr/bin/python3\n"
            "import pathlib, sys\n"
            "stage = pathlib.Path(sys.argv[sys.argv.index('--dir') + 1])\n"
            "index = stage / 'index.html'\n"
            "text = index.read_text()\n"
            "if 'The experiment has not begun.' in text:\n"
            "    text = text.replace('The experiment has not begun.', 'Evolution one is live.')\n"
            "elif 'Evolution one is live.' in text:\n"
            "    text = text.replace('Evolution one is live.', 'Evolution two inherited one.')\n"
            "else:\n"
            "    text += '<!-- another material turn -->'\n"
            "index.write_text(text)\n"
            "print('{\"type\":\"text\",\"text\":\"done\"}')\n",
            encoding="utf-8",
        )
        fake.chmod(0o755)

        config = replace(
            source_config,
            repo=root,
            site_dir=site,
            state_dir=state,
            models=("ollama/fake",),
            opencode=OpenCodeConfig(binary=fake, version="test"),
            publish=PublishConfig(
                remote="unused",
                main_branch="main",
                deploy_key=root / ".secrets" / "key",
            ),
        )
        return config

    def _static_validation(self, site, config, screenshots, *, browser):
        self.assertTrue(browser, "runner must always request browser validation")
        return validate_static(site, config)

    def _run(self, config):
        with (
            patch("agent_lab.runner._unload_model"),
            patch(
                "agent_lab.runner.validate_site",
                side_effect=self._static_validation,
            ),
        ):
            return run_once(config)

    def test_valid_fake_agent_is_spooled_without_raw_output(self) -> None:
        with TemporaryDirectory() as temporary:
            config = self._fixture(Path(temporary))
            config.state_dir.mkdir(mode=0o755)
            record = self._run(config)

            self.assertTrue(record["accepted"], record)
            self.assertEqual(record["status"], "accepted")
            self.assertEqual(record["changed_files"], ["index.html"])
            self.assertNotIn("final_output_excerpt", record)
            spool = config.state_dir / "spool" / f"{record['run_id']}.json"
            self.assertTrue(spool.is_file())
            saved = json.loads(spool.read_text(encoding="utf-8"))
            self.assertEqual(saved["model"], "ollama/fake")
            self.assertEqual(config.state_dir.stat().st_mode & 0o077, 0)

    def test_accepted_candidate_is_fsynced_before_spooling(self) -> None:
        with TemporaryDirectory() as temporary:
            config = self._fixture(Path(temporary))
            events: list[tuple[str, Path]] = []
            real_atomic_write_json = runner_module.atomic_write_json

            def durable_write(path, value):
                if path.parent == config.state_dir / "spool":
                    events.append(("spool", path))
                return real_atomic_write_json(path, value)

            with (
                patch(
                    "agent_lab.runner.fsync_tree",
                    side_effect=lambda path: events.append(("fsync", path)),
                ),
                patch(
                    "agent_lab.runner.atomic_write_json",
                    side_effect=durable_write,
                ),
            ):
                record = self._run(config)

            candidate = config.state_dir / "raw" / str(record["run_id"]) / "candidate"
            self.assertTrue(record["accepted"])
            self.assertIn(("fsync", candidate), events)
            self.assertLess(
                events.index(("fsync", candidate)),
                next(index for index, event in enumerate(events) if event[0] == "spool"),
            )

    def test_run_rejects_an_overcommitted_service_budget_before_reserving(self) -> None:
        with TemporaryDirectory() as temporary:
            config = self._fixture(Path(temporary))
            (config.repo / "lab" / "systemd" / "agent-farm-run.service").write_text(
                "[Service]\nTimeoutStartSec=30min\n",
                encoding="utf-8",
            )

            with patch("agent_lab.runner._run_opencode") as launch:
                with self.assertRaisesRegex(RuntimeError, "does not fit"):
                    run_once(config)

            launch.assert_not_called()
            self.assertFalse((config.state_dir / "scheduler.json").exists())

    def test_second_turn_inherits_successfully_published_lineage(self) -> None:
        with TemporaryDirectory() as temporary:
            config = self._fixture(Path(temporary))
            first = self._run(config)
            first_run = config.state_dir / "raw" / str(first["run_id"])
            update_lineage(config, first_run / "candidate")
            (config.state_dir / "spool" / f"{first['run_id']}.json").unlink()

            second = self._run(config)
            second_run = config.state_dir / "raw" / str(second["run_id"])

            self.assertTrue(second["accepted"], second)
            self.assertIn(
                "Evolution one is live.",
                (second_run / "baseline" / "index.html").read_text(encoding="utf-8"),
            )
            self.assertIn(
                "Evolution two inherited one.",
                (second_run / "candidate" / "index.html").read_text(encoding="utf-8"),
            )
            self.assertIn(
                "The experiment has not begun.",
                (config.site_dir / "index.html").read_text(encoding="utf-8"),
            )
            lineage = ensure_lineage(config)
            self.assertEqual(
                (lineage / "index.html").read_text(encoding="utf-8"),
                (first_run / "candidate" / "index.html").read_text(encoding="utf-8"),
            )

    def test_lineage_finishes_an_interrupted_directory_replacement(self) -> None:
        with TemporaryDirectory() as temporary:
            config = self._fixture(Path(temporary))
            lineage = ensure_lineage(config)
            root = lineage.parent
            incoming = root / ".site.next-test"
            shutil.copytree(lineage, incoming)
            index = incoming / "index.html"
            index.write_text(
                index.read_text(encoding="utf-8").replace(
                    "The experiment has not begun.", "Recovered lineage is live."
                ),
                encoding="utf-8",
            )
            atomic_write_json(
                root / "replacement.json",
                {"schema_version": 1, "next": incoming.name},
            )
            lineage.rename(root / ".site.previous")

            recovered = ensure_lineage(config)

            self.assertIn(
                "Recovered lineage is live.",
                (recovered / "index.html").read_text(encoding="utf-8"),
            )
            self.assertFalse((root / "replacement.json").exists())
            self.assertFalse((root / ".site.previous").exists())

    def test_pending_publication_does_not_launch_or_consume_a_turn(self) -> None:
        with TemporaryDirectory() as temporary:
            config = self._fixture(Path(temporary))
            first = self._run(config)
            before = json.loads(
                (config.state_dir / "scheduler.json").read_text(encoding="utf-8")
            )
            with patch("agent_lab.runner._run_opencode") as launch:
                result = run_once(config)

            launch.assert_not_called()
            self.assertEqual(result["status"], "publication_pending")
            self.assertEqual(result["run_id"], first["run_id"])
            after = json.loads(
                (config.state_dir / "scheduler.json").read_text(encoding="utf-8")
            )
            self.assertEqual(after["position"], before["position"])

    def test_stale_inflight_is_spooled_as_interrupted_once(self) -> None:
        with TemporaryDirectory() as temporary:
            config = self._fixture(Path(temporary))
            config.state_dir.mkdir()
            scheduler = SchedulerState(
                config.state_dir / "scheduler.json",
                config.model_pool_version,
                config.models,
            )
            scheduler.reserve("abandoned")

            with patch("agent_lab.runner._run_opencode") as launch:
                recovered = run_once(config)
                pending = run_once(config)

            launch.assert_not_called()
            self.assertEqual(recovered["status"], "interrupted")
            self.assertFalse(recovered["accepted"])
            self.assertEqual(pending["status"], "publication_pending")
            state = json.loads(
                (config.state_dir / "scheduler.json").read_text(encoding="utf-8")
            )
            self.assertEqual(state["position"], 1)
            self.assertIsNone(state["inflight"])
            self.assertTrue((config.state_dir / "spool" / "abandoned.json").is_file())

    def test_final_record_survives_if_publisher_removed_spool_before_complete(self) -> None:
        with TemporaryDirectory() as temporary:
            config = self._fixture(Path(temporary))
            with patch(
                "agent_lab.runner.SchedulerState.complete",
                side_effect=RuntimeError("simulated completion crash"),
            ):
                with self.assertRaisesRegex(RuntimeError, "simulated completion crash"):
                    self._run(config)

            state = json.loads(
                (config.state_dir / "scheduler.json").read_text(encoding="utf-8")
            )
            run_id = state["inflight"]["run_id"]
            run_dir = config.state_dir / "raw" / run_id
            record = json.loads((run_dir / "record.json").read_text(encoding="utf-8"))
            spool_path = config.state_dir / "spool" / f"{run_id}.json"
            self.assertTrue(spool_path.is_file())
            spool_path.unlink()

            with patch("agent_lab.runner._run_opencode") as launch:
                recovered = run_once(config)

            launch.assert_not_called()
            self.assertEqual(recovered, record)
            self.assertTrue(recovered["accepted"])
            self.assertTrue(
                (config.state_dir / "spool" / f"{run_id}.json").is_file()
            )
            completed = json.loads(
                (config.state_dir / "scheduler.json").read_text(encoding="utf-8")
            )
            self.assertEqual(completed["position"], 1)
            self.assertIsNone(completed["inflight"])

    def test_malformed_final_record_is_quarantined_and_interrupted(self) -> None:
        with TemporaryDirectory() as temporary:
            config = self._fixture(Path(temporary))
            config.state_dir.mkdir()
            scheduler = SchedulerState(
                config.state_dir / "scheduler.json",
                config.model_pool_version,
                config.models,
            )
            reservation = scheduler.reserve("malformed-record")
            run_dir = config.state_dir / "raw" / reservation.run_id
            run_dir.mkdir(parents=True)
            atomic_write_json(
                run_dir / "record.json",
                {
                    "schema_version": 1,
                    "run_id": reservation.run_id,
                    "model": reservation.model,
                    "pool_version": reservation.pool_version,
                    "epoch": reservation.epoch,
                    "epoch_position": reservation.epoch_position,
                    "status": "accepted",
                    "accepted": True,
                },
            )

            with patch("agent_lab.runner._run_opencode") as launch:
                recovered = run_once(config)

            launch.assert_not_called()
            self.assertEqual(recovered["status"], "interrupted")
            self.assertFalse(recovered["accepted"])
            self.assertTrue((run_dir / "record.invalid.json").is_file())
            saved = json.loads((run_dir / "record.json").read_text(encoding="utf-8"))
            self.assertEqual(saved, recovered)
            self.assertTrue(
                (config.state_dir / "spool" / "malformed-record.json").is_file()
            )

    def test_complete_interrupted_record_survives_spool_race(self) -> None:
        with TemporaryDirectory() as temporary:
            config = self._fixture(Path(temporary))
            config.state_dir.mkdir()
            scheduler = SchedulerState(
                config.state_dir / "scheduler.json",
                config.model_pool_version,
                config.models,
            )
            scheduler.reserve("interrupted-race")
            with patch(
                "agent_lab.runner.SchedulerState.complete",
                side_effect=RuntimeError("simulated recovery completion crash"),
            ):
                with self.assertRaisesRegex(
                    RuntimeError, "simulated recovery completion crash"
                ):
                    run_once(config)

            run_dir = config.state_dir / "raw" / "interrupted-race"
            record = json.loads((run_dir / "record.json").read_text(encoding="utf-8"))
            (config.state_dir / "spool" / "interrupted-race.json").unlink()

            with patch("agent_lab.runner._run_opencode") as launch:
                recovered = run_once(config)

            launch.assert_not_called()
            self.assertEqual(recovered, record)
            self.assertEqual(recovered["status"], "interrupted")
            self.assertTrue(
                (config.state_dir / "spool" / "interrupted-race.json").is_file()
            )

    def test_accepted_record_without_candidate_becomes_interrupted(self) -> None:
        with TemporaryDirectory() as temporary:
            config = self._fixture(Path(temporary))
            with patch(
                "agent_lab.runner.SchedulerState.complete",
                side_effect=RuntimeError("simulated completion crash"),
            ):
                with self.assertRaisesRegex(RuntimeError, "simulated completion crash"):
                    self._run(config)

            state = json.loads(
                (config.state_dir / "scheduler.json").read_text(encoding="utf-8")
            )
            run_id = state["inflight"]["run_id"]
            run_dir = config.state_dir / "raw" / run_id
            (config.state_dir / "spool" / f"{run_id}.json").unlink()
            shutil.rmtree(run_dir / "candidate")

            with patch("agent_lab.runner._run_opencode") as launch:
                recovered = run_once(config)

            launch.assert_not_called()
            self.assertEqual(recovered["status"], "interrupted")
            self.assertFalse(recovered["accepted"])
            self.assertTrue((run_dir / "record.invalid.json").is_file())

    def test_spooled_inflight_is_reconciled_without_new_turn(self) -> None:
        with TemporaryDirectory() as temporary:
            config = self._fixture(Path(temporary))
            config.state_dir.mkdir()
            spool = config.state_dir / "spool"
            spool.mkdir()
            scheduler = SchedulerState(
                config.state_dir / "scheduler.json",
                config.model_pool_version,
                config.models,
            )
            scheduler.reserve("already-spooled")
            atomic_write_json(spool / "already-spooled.json", {"run_id": "already-spooled"})

            with patch("agent_lab.runner._run_opencode") as launch:
                result = run_once(config)

            launch.assert_not_called()
            self.assertEqual(result["status"], "publication_pending")
            self.assertTrue(result["scheduler_reconciled"])
            state = json.loads(
                (config.state_dir / "scheduler.json").read_text(encoding="utf-8")
            )
            self.assertEqual(state["position"], 1)
            self.assertIsNone(state["inflight"])
