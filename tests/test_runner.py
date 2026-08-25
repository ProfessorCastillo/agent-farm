import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from agent_lab.config import OpenCodeConfig, PublishConfig, load_config
from agent_lab.runner import run_once


class RunnerIntegrationTests(TestCase):
    def test_valid_fake_agent_is_spooled(self) -> None:
        source_config = load_config(Path("lab/config.toml"))
        with TemporaryDirectory() as temporary:
            repo = Path(temporary)
            site = repo / "site"
            state = repo / ".lab-state"
            lab = repo / "lab"
            runtime = repo / ".runtime"
            site.mkdir()
            lab.mkdir()
            runtime.mkdir()
            (lab / "opencode.json").write_text("{}")
            initial = Path("site/index.html").read_text()
            (site / "index.html").write_text(initial)

            fake = runtime / "fake-opencode"
            fake.write_text(
                "#!/usr/bin/python3\n"
                "import pathlib, sys\n"
                "stage = pathlib.Path(sys.argv[sys.argv.index('--dir') + 1])\n"
                "index = stage / 'index.html'\n"
                "index.write_text(index.read_text().replace("
                "'The experiment has not begun.', 'A useful change appeared.'))\n"
                "print('{\"type\":\"text\",\"text\":\"done\"}')\n"
            )
            fake.chmod(0o755)

            config = replace(
                source_config,
                repo=repo,
                site_dir=site,
                state_dir=state,
                models=("ollama/fake",),
                opencode=OpenCodeConfig(binary=fake, version="test"),
                publish=PublishConfig(
                    remote="unused",
                    main_branch="main",
                    deploy_key=repo / ".secrets" / "key",
                ),
            )
            with patch("agent_lab.runner._unload_model"):
                record = run_once(config, browser=False)

            self.assertTrue(record["accepted"], record)
            self.assertEqual(record["status"], "accepted")
            self.assertEqual(record["changed_files"], ["index.html"])
            spool = state / "spool" / f"{record['run_id']}.json"
            self.assertTrue(spool.is_file())
            saved = json.loads(spool.read_text())
            self.assertEqual(saved["model"], "ollama/fake")

