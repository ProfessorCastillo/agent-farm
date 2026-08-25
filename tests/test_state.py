import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from agent_lab.state import SchedulerState


class SchedulerTests(TestCase):
    def test_epoch_uses_each_model_once(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "scheduler.json"
            models = ("ollama/a", "ollama/b", "ollama/c")
            seen = []
            with patch("agent_lab.state.secrets.randbits", return_value=42):
                for index in range(3):
                    state = SchedulerState(path, 1, models)
                    reservation = state.reserve(f"run-{index}")
                    seen.append(reservation.model)
                    state.complete(reservation.run_id)
            self.assertEqual(set(seen), set(models))
            data = json.loads(path.read_text())
            self.assertEqual(data["position"], 3)
            self.assertIsNone(data["inflight"])

    def test_pool_change_is_rejected_mid_epoch(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "scheduler.json"
            state = SchedulerState(path, 1, ("ollama/a", "ollama/b"))
            reservation = state.reserve("run-1")
            state.complete(reservation.run_id)
            with self.assertRaisesRegex(ValueError, "before the current epoch completed"):
                SchedulerState(path, 2, ("ollama/a", "ollama/c"))

    def test_inflight_reservation_blocks_different_run(self) -> None:
        with TemporaryDirectory() as temporary:
            state = SchedulerState(
                Path(temporary) / "scheduler.json",
                1,
                ("ollama/a",),
            )
            state.reserve("run-1")
            with self.assertRaisesRegex(RuntimeError, "unfinished run"):
                state.reserve("run-2")

    def test_completion_advances_a_reservation_exactly_once(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "scheduler.json"
            state = SchedulerState(path, 1, ("ollama/a",))
            state.reserve("run-1")
            state.complete("run-1")
            with self.assertRaisesRegex(RuntimeError, "not reserved"):
                state.complete("run-1")
            self.assertEqual(json.loads(path.read_text())["position"], 1)
