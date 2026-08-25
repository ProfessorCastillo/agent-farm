from pathlib import Path
from unittest import TestCase

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

