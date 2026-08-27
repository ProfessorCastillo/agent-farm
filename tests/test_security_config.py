import json
import subprocess
from pathlib import Path
from unittest import TestCase


ROOT = Path(__file__).resolve().parent.parent


class SecurityConfigurationTests(TestCase):
    def test_opencode_has_no_shell_or_external_tools(self) -> None:
        config = json.loads((ROOT / "lab" / "opencode.json").read_text(encoding="utf-8"))
        permissions = config["permission"]
        self.assertEqual(permissions["bash"], "deny")
        self.assertEqual(permissions["external_directory"], "deny")
        for name in ("webfetch", "websearch", "task", "skill", "question"):
            self.assertEqual(permissions[name], "deny")

    def test_isolation_probe_has_valid_shell_syntax(self) -> None:
        subprocess.run(
            ["bash", "-n", str(ROOT / "scripts" / "probe-system-isolation.sh")],
            check=True,
            capture_output=True,
            text=True,
        )

    def test_runner_hides_home_and_blocks_external_network(self) -> None:
        unit = (ROOT / "lab" / "systemd" / "agent-farm-run.service").read_text(
            encoding="utf-8"
        )
        self.assertIn("ProtectHome=tmpfs", unit)
        binds = {
            line
            for line in unit.splitlines()
            if line.startswith("BindReadOnlyPaths=")
        }
        self.assertNotIn(
            "BindReadOnlyPaths=/home/adminvince/projects/agent_farm", binds
        )
        for relative in (".venv", ".runtime", "agent_lab", "lab", "site"):
            self.assertIn(
                f"BindReadOnlyPaths=/home/adminvince/projects/agent_farm/{relative}",
                binds,
            )
        self.assertIn("InaccessiblePaths=-/home/adminvince/projects/agent_farm/.secrets", unit)
        self.assertIn("IPAddressDeny=any", unit)
        self.assertIn("IPAddressAllow=localhost", unit)
        self.assertIn(
            "BindPaths=/home/adminvince/projects/agent_farm/.lab-state", unit
        )
        self.assertIn("ProtectProc=invisible", unit)
        self.assertIn("ProcSubset=pid", unit)

    def test_publisher_has_an_independent_retry_timer(self) -> None:
        timer = (ROOT / "lab" / "systemd" / "agent-farm-publish.timer").read_text(
            encoding="utf-8"
        )
        installer = (ROOT / "scripts" / "install-system-units.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("OnUnitInactiveSec=5min", timer)
        self.assertIn("agent-farm-publish.timer", installer)
        self.assertIn('install -d -m 0700 "${repo}/.lab-state"', installer)

    def test_runner_does_not_fire_immediately_when_enabled_after_boot(self) -> None:
        timer = (ROOT / "lab" / "systemd" / "agent-farm-run.timer").read_text(
            encoding="utf-8"
        )
        self.assertIn("OnActiveSec=10min", timer)
        self.assertNotIn("OnBootSec=", timer)

    def test_publisher_hides_unrelated_home_content(self) -> None:
        unit = (ROOT / "lab" / "systemd" / "agent-farm-publish.service").read_text(
            encoding="utf-8"
        )
        self.assertIn("ProtectHome=tmpfs", unit)
        binds = {
            line
            for line in unit.splitlines()
            if line.startswith("BindReadOnlyPaths=")
        }
        self.assertNotIn(
            "BindReadOnlyPaths=/home/adminvince/projects/agent_farm", binds
        )
        for relative in (".venv", ".runtime", "agent_lab", "lab", ".secrets"):
            self.assertIn(
                f"BindReadOnlyPaths=/home/adminvince/projects/agent_farm/{relative}",
                binds,
            )
        self.assertIn("ReadOnlyPaths=/home/adminvince/projects/agent_farm/.secrets", unit)
        self.assertIn(
            "BindPaths=/home/adminvince/projects/agent_farm/.lab-state", unit
        )

    def test_prompt_discloses_the_canonical_csp(self) -> None:
        prompt_config = (ROOT / "lab" / "config.toml").read_text(encoding="utf-8")
        self.assertIn("Content-Security-Policy", prompt_config)
        self.assertIn("connect-src 'none'", prompt_config)
