from __future__ import annotations

import re

from .config import LabConfig


OPENCODE_TERMINATE_TIMEOUT_SECONDS = 10
OPENCODE_KILL_TIMEOUT_SECONDS = 10
MODEL_UNLOAD_TIMEOUT_SECONDS = 60
POSTPROCESS_BUDGET_SECONDS = 300


def runner_service_timeout_seconds(config: LabConfig) -> int:
    unit = config.repo / "lab" / "systemd" / "agent-farm-run.service"
    text = unit.read_text(encoding="utf-8")
    matches = re.findall(r"^TimeoutStartSec=(\d+)(s|min|h)?$", text, re.MULTILINE)
    if len(matches) != 1:
        raise RuntimeError("runner unit must declare exactly one simple TimeoutStartSec")
    amount_text, unit_name = matches[0]
    multiplier = {"": 1, "s": 1, "min": 60, "h": 3600}[unit_name]
    return int(amount_text) * multiplier


def runner_budget(config: LabConfig) -> dict[str, int]:
    service_timeout = runner_service_timeout_seconds(config)
    required = (
        config.turn_timeout_seconds
        + OPENCODE_TERMINATE_TIMEOUT_SECONDS
        + OPENCODE_KILL_TIMEOUT_SECONDS
        + MODEL_UNLOAD_TIMEOUT_SECONDS
        + config.validation.browser_total_timeout_seconds
        + POSTPROCESS_BUDGET_SECONDS
    )
    if required >= service_timeout:
        raise RuntimeError(
            f"runner worst-case budget {required}s does not fit inside "
            f"TimeoutStartSec={service_timeout}s"
        )
    return {
        "required_seconds": required,
        "service_timeout_seconds": service_timeout,
        "reserve_seconds": service_timeout - required,
    }
