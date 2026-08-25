#!/usr/bin/env bash
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
node_version="22.22.0"
node_archive="node-v${node_version}-linux-x64.tar.xz"
node_sha256="9aa8e9d2298ab68c600bd6fb86a6c13bce11a4eca1ba9b39d79fa021755d7c37"
runtime="${repo}/.runtime"

python3 -m venv "${repo}/.venv"
"${repo}/.venv/bin/python" -m pip install --requirement "${repo}/requirements.lock"

mkdir -p "${runtime}"
if [[ ! -x "${runtime}/node/bin/node" ]]; then
  archive="${runtime}/${node_archive}"
  curl --fail --location --output "${archive}" \
    "https://nodejs.org/dist/v${node_version}/${node_archive}"
  printf '%s  %s\n' "${node_sha256}" "${archive}" | sha256sum --check -
  mkdir -p "${runtime}/node"
  tar --extract --xz --file "${archive}" \
    --strip-components=1 --directory "${runtime}/node"
  rm -- "${archive}"
fi

mkdir -p "${runtime}/opencode"
cp "${repo}/lab/runtime-package.json" "${runtime}/opencode/package.json"
PATH="${runtime}/node/bin:/usr/bin:/bin" \
  "${runtime}/node/bin/npm" install \
  --prefix "${runtime}/opencode" \
  --omit=dev \
  --no-audit \
  --no-fund

PLAYWRIGHT_BROWSERS_PATH="${runtime}/playwright" \
  "${repo}/.venv/bin/python" -m playwright install chromium

"${repo}/.venv/bin/python" -m agent_lab.cli preflight || true
printf '\nRuntime installed. The deploy-key check is expected to fail until GitHub setup is complete.\n'

