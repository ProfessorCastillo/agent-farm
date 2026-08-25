from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from agent_lab.budget import runner_budget
from agent_lab.config import load_config


class ConfigTests(TestCase):
    def test_v1_model_pool_is_explicit_and_unique(self) -> None:
        config = load_config(Path("lab/config.toml"))
        self.assertEqual(len(config.models), 10)
        self.assertEqual(len(set(config.models)), 10)
        self.assertIn("ollama/gemma4:31b", config.models)
        self.assertIn("ollama/gpt-oss:20b-131k", config.models)
        self.assertNotIn("ollama/gpt-oss:20b", config.models)

    def test_runtime_paths_remain_inside_repository(self) -> None:
        config = load_config(Path("lab/config.toml"))
        self.assertTrue(config.site_dir.is_relative_to(config.repo))
        self.assertTrue(config.state_dir.is_relative_to(config.repo))
        self.assertTrue(config.opencode.binary.is_relative_to(config.repo))

    def test_integer_fields_reject_booleans(self) -> None:
        source = Path("lab/config.toml").read_text(encoding="utf-8")
        invalid = source.replace("model_pool_version = 1", "model_pool_version = true")
        with TemporaryDirectory() as temporary:
            lab = Path(temporary) / "lab"
            lab.mkdir()
            path = lab / "config.toml"
            path.write_text(invalid, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "model_pool_version must be int"):
                load_config(path)

    def test_browser_validation_has_a_total_deadline(self) -> None:
        config = load_config(Path("lab/config.toml"))
        self.assertGreater(config.validation.browser_total_timeout_seconds, 0)
        self.assertEqual(config.validation.max_files, 500)

    def test_runner_budget_fits_systemd_timeout(self) -> None:
        budget = runner_budget(load_config(Path("lab/config.toml")))
        self.assertGreater(budget["reserve_seconds"], 0)
        self.assertEqual(budget["service_timeout_seconds"], 45 * 60)
