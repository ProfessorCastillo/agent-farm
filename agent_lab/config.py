from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class OpenCodeConfig:
    binary: Path
    version: str


@dataclass(frozen=True)
class ValidationConfig:
    max_site_bytes: int
    max_file_bytes: int
    max_pages: int
    browser_timeout_seconds: int
    require_browser: bool


@dataclass(frozen=True)
class PublishConfig:
    remote: str
    main_branch: str
    deploy_key: Path


@dataclass(frozen=True)
class LabConfig:
    repo: Path
    site_dir: Path
    state_dir: Path
    observations_branch: str
    model_pool_version: int
    turn_timeout_seconds: int
    raw_retention_days: int
    raw_retention_bytes: int
    prompt: str
    models: tuple[str, ...]
    opencode: OpenCodeConfig
    validation: ValidationConfig
    publish: PublishConfig


def _require(data: dict[str, Any], key: str, expected: type) -> Any:
    value = data.get(key)
    if not isinstance(value, expected):
        raise ValueError(f"{key} must be {expected.__name__}")
    return value


def _inside(repo: Path, value: str, name: str) -> Path:
    candidate = (repo / value).resolve()
    try:
        candidate.relative_to(repo)
    except ValueError as exc:
        raise ValueError(f"{name} must remain inside the repository") from exc
    return candidate


def load_config(path: Path) -> LabConfig:
    path = path.resolve()
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    if data.get("schema_version") != 1:
        raise ValueError("unsupported config schema_version")

    repo = path.parent.parent.resolve()
    models = tuple(_require(data, "models", list))
    if not models or len(models) != len(set(models)):
        raise ValueError("models must be a non-empty unique list")
    if any(not isinstance(model, str) or not model.startswith("ollama/") for model in models):
        raise ValueError("every model must use an ollama/ identifier")

    opencode_data = _require(data, "opencode", dict)
    validation_data = _require(data, "validation", dict)
    publish_data = _require(data, "publish", dict)

    return LabConfig(
        repo=repo,
        site_dir=_inside(repo, _require(data, "site_dir", str), "site_dir"),
        state_dir=_inside(repo, _require(data, "state_dir", str), "state_dir"),
        observations_branch=_require(data, "observations_branch", str),
        model_pool_version=int(_require(data, "model_pool_version", int)),
        turn_timeout_seconds=int(_require(data, "turn_timeout_seconds", int)),
        raw_retention_days=int(_require(data, "raw_retention_days", int)),
        raw_retention_bytes=int(_require(data, "raw_retention_bytes", int)),
        prompt=_require(data, "prompt", str).strip(),
        models=models,
        opencode=OpenCodeConfig(
            binary=_inside(repo, _require(opencode_data, "binary", str), "opencode.binary"),
            version=_require(opencode_data, "version", str),
        ),
        validation=ValidationConfig(
            max_site_bytes=int(_require(validation_data, "max_site_bytes", int)),
            max_file_bytes=int(_require(validation_data, "max_file_bytes", int)),
            max_pages=int(_require(validation_data, "max_pages", int)),
            browser_timeout_seconds=int(
                _require(validation_data, "browser_timeout_seconds", int)
            ),
            require_browser=bool(_require(validation_data, "require_browser", bool)),
        ),
        publish=PublishConfig(
            remote=_require(publish_data, "remote", str),
            main_branch=_require(publish_data, "main_branch", str),
            deploy_key=_inside(repo, _require(publish_data, "deploy_key", str), "publish.deploy_key"),
        ),
    )

