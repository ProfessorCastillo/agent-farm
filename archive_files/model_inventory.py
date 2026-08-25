#!/usr/bin/env python3

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

MODELS = [
    "ornith-1.5:9b",
    "ornith-1.5:35b",
    "nemotron-3.5-lightning:30b",
    "muse-glimmer:30b",
    "qwen3.8:27b",
    "qwen3.5:9b",
    "qwen3.6:35b",
    "gemma4:31b",
    "gemma4:26b",
    "qwen3.5:27b",
    "qwen3.5:35b",
    "gpt-oss:20b-131k",
    "ministral-3:14b",
    "ministral-3:8b",
    "devstral-small-2:24b",
    "nemotron-3-nano:30b",
]

OUTPUT = Path("model-list.md")


def run(*args):
    return subprocess.run(
        args, text=True, capture_output=True, check=True
    ).stdout


def installed_models():
    """Extract ID and installed size from the human-readable model list."""
    inventory = {}

    for line in run("ollama", "list").splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 4:
            name, model_id, size, unit = fields[:4]
            inventory[name] = {
                "id": model_id,
                "size": f"{size} {unit}",
            }

    return inventory


def show_model(name):
    """Return machine-readable `ollama show` output."""
    raw = run("ollama", "show", "-v", name)
    return parse_ollama_show(raw)


def parse_ollama_show(text):
    """Parse verbose `ollama show` output into details/model_info/capabilities."""
    alias = {
        "architecture": "family",
        "parameters": "parameter_size",
        "quantization": "quantization_level",
        "context length": "context_length",
        "embedding length": "embedding_length",
    }

    details = {}
    model_info = {}
    capabilities = []
    param_lines = []
    section = "Model"

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= 2:
            section = stripped
            continue

        parts = re.split(r"\s{2,}", stripped, maxsplit=1)
        if len(parts) == 2:
            key, value = (part.strip() for part in parts)
        else:
            key, value = None, stripped

        if section == "Capabilities" and value is not None:
            capabilities.append(value)
        elif section == "Parameters" and key is not None:
            param_lines.append(f"{key} {value}")
        elif section == "Model" and key is not None:
            if key in alias:
                details[alias[key]] = value
            else:
                details[key.replace(" ", "_")] = value
        elif section == "Metadata" and key is not None:
            model_info[key] = value
            if key.endswith(".context_length"):
                model_info["context_length"] = value
            elif key.endswith(".expert_count"):
                model_info["expert_count"] = value
            elif key.endswith(".expert_used_count"):
                model_info["expert_used_count"] = value

    return {
        "details": details,
        "model_info": model_info,
        "capabilities": capabilities,
        "parameters": "\n".join(param_lines),
    }


def format_number(value):
    if value in (None, ""):
        return "—"

    try:
        value = float(value)
    except (TypeError, ValueError):
        return str(value)

    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"

    return f"{value:,.0f}"


def human_count(value):
    try:
        return f"{int(float(value)):,}"
    except (TypeError, ValueError):
        return "—"


def configured_context(show):
    """Find a num_ctx override, if the Modelfile defines one."""
    match = re.search(
        r"^num_ctx\s+(\d+)",
        show.get("parameters", ""),
        re.MULTILINE | re.IGNORECASE,
    )
    return f"{int(match.group(1)):,}" if match else "—"


def main():
    installed = installed_models()
    rows = []
    errors = []

    for name in MODELS:
        try:
            show = show_model(name)
            details = show.get("details", {})
            info = show.get("model_info", {})

            if info.get("context_length") is None:
                info["context_length"] = details.get("context_length")

            native_context = human_count(info.get("context_length"))
            expert_count = info.get("expert_count")
            active_experts = info.get("expert_used_count")

            if expert_count:
                experts = str(expert_count)
                if active_experts:
                    experts += f" / {active_experts} active"
            else:
                experts = "Dense"

            local = installed.get(name, {})

            rows.append([
                name,
                local.get("id", "—"),
                local.get("size", "—"),
                details.get("family") or "—",
                details.get("parameter_size")
                or format_number(info.get("general.parameter_count")),
                details.get("quantization_level") or "—",
                native_context,
                configured_context(show),
                experts,
                ", ".join(show.get("capabilities", [])) or "—",
            ])

        except Exception as exc:
            errors.append(f"- `{name}`: {exc}")

    headers = [
        "Model",
        "ID",
        "Disk size",
        "Architecture",
        "Parameters",
        "Quant",
        "Native context",
        "num_ctx override",
        "Experts",
        "Capabilities",
    ]

    lines = [
        "# Ollama Participant Model Inventory",
        "",
        f"Generated: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        "",
        "> Native context is the model metadata limit. It is not necessarily "
        "the context Ollama allocates when the model runs.",
        "",
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]

    for row in rows:
        lines.append(
            "| " + " | ".join(str(value).replace("|", "\\|") for value in row) + " |"
        )

    if errors:
        lines.extend(["", "## Errors", "", *errors])

    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT.resolve()} with {len(rows)} models.")

    if errors:
        print(f"{len(errors)} model(s) could not be inspected.")


if __name__ == "__main__":
    main()
