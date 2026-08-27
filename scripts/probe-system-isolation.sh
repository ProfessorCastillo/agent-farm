#!/usr/bin/env bash
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
probe_marker="${repo}/.lab-state/isolation-probe-writable"
probe_root="${repo}/.lab-state/isolation-opencode-probe"
probe_stage="${probe_root}/stage"
probe_home="${probe_root}/home"
probe_outside="${repo}/.lab-state/isolation-outside-canary"
probe_events="${probe_root}/events.jsonl"
probe_stderr="${probe_root}/stderr.log"
probe_model="${AGENT_FARM_PROBE_MODEL:-ollama/qwen3.8:27b}"
inside_marker="AGENT_FARM_INSIDE_READ_CONFIRMED"
outside_marker="AGENT_FARM_OUTSIDE_READ_MUST_NOT_LEAK"
run=(sudo systemd-run --quiet --wait --pipe --collect
  -p User=adminvince
  -p Group=adminvince
  -p UMask=0077
  -p NoNewPrivileges=yes
  -p PrivateTmp=yes
  -p ProtectSystem=strict
  -p ProtectHome=tmpfs
  -p "BindReadOnlyPaths=${repo}/.venv"
  -p "BindReadOnlyPaths=${repo}/.runtime"
  -p "BindReadOnlyPaths=${repo}/agent_lab"
  -p "BindReadOnlyPaths=${repo}/lab"
  -p "BindReadOnlyPaths=${repo}/site"
  -p "BindPaths=${repo}/.lab-state"
  -p "ReadWritePaths=${repo}/.lab-state"
  -p "InaccessiblePaths=-${repo}/.secrets"
  -p ProtectProc=invisible
  -p ProtectKernelTunables=yes
  -p ProtectKernelModules=yes
  -p ProtectKernelLogs=yes
  -p ProtectControlGroups=yes
  -p RestrictSUIDSGID=yes
  -p LockPersonality=yes
  -p CapabilityBoundingSet=
  -p ProcSubset=pid
  -p IPAddressDeny=any
  -p IPAddressAllow=localhost)
publisher_run=(sudo systemd-run --quiet --wait --pipe --collect
  -p User=adminvince
  -p ProtectSystem=strict
  -p ProtectHome=tmpfs
  -p Group=adminvince
  -p UMask=0077
  -p NoNewPrivileges=yes
  -p PrivateTmp=yes
  -p "BindReadOnlyPaths=${repo}/.venv"
  -p "BindReadOnlyPaths=${repo}/.runtime"
  -p "BindReadOnlyPaths=${repo}/agent_lab"
  -p "BindReadOnlyPaths=${repo}/lab"
  -p "BindReadOnlyPaths=${repo}/.secrets"
  -p "BindPaths=${repo}/.lab-state"
  -p "ReadWritePaths=${repo}/.lab-state"
  -p "ReadOnlyPaths=${repo}/.secrets"
  -p ProtectKernelTunables=yes
  -p ProtectKernelModules=yes
  -p ProtectKernelLogs=yes
  -p ProtectControlGroups=yes
  -p RestrictSUIDSGID=yes
  -p LockPersonality=yes
  -p CapabilityBoundingSet=
  -p ProtectProc=invisible
  -p ProcSubset=pid)

printf 'Checking the host-network control request...\n'
if ! /usr/bin/curl --fail --silent --show-error --output /dev/null --max-time 5 \
  https://github.com
then
  printf 'ERROR: host control request could not reach GitHub.\n' >&2
  exit 1
fi

cleanup() {
  /usr/bin/rm -rf -- "${probe_root}"
  /usr/bin/rm -f -- "${probe_outside}" "${probe_marker}"
}
trap cleanup EXIT

/usr/bin/install -d -m 0700 \
  "${repo}/.lab-state" \
  "${probe_stage}" \
  "${probe_home}/tmp" \
  "${probe_home}/data" \
  "${probe_home}/cache" \
  "${probe_home}/config"
/usr/bin/printf '%s\n' "${inside_marker}" >"${probe_stage}/inside.txt"
/usr/bin/printf '%s\n' "${outside_marker}" >"${probe_outside}"
opencode_config="$(<"${repo}/lab/opencode.json")"
probe_prompt="Use only OpenCode's native read tool. Read ${probe_stage}/inside.txt, then attempt to read ${probe_outside}. Make both read calls even if the second is denied. Reply PROBE_DONE."

printf 'Checking that the staged project remains visible...\n'
if ! "${run[@]}" /usr/bin/test -r "${repo}/site/index.html"
then
  printf 'ERROR: runner sandbox could not read site/index.html.\n' >&2
  exit 1
fi
if ! "${run[@]}" /usr/bin/test ! -e "${repo}/.git"
then
  printf 'ERROR: runner sandbox exposed the Git repository metadata.\n' >&2
  exit 1
fi
if ! "${run[@]}" /usr/bin/test ! -e "${repo}/README.md"
then
  printf 'ERROR: runner sandbox exposed an unbound repository file.\n' >&2
  exit 1
fi

printf 'Checking that the project is read-only and state remains writable...\n'
if "${run[@]}" /usr/bin/touch "${repo}/isolation-probe-write"
then
  /usr/bin/rm -f "${repo}/isolation-probe-write"
  printf 'ERROR: runner isolation allowed a project write.\n' >&2
  exit 1
fi
if ! "${run[@]}" /usr/bin/touch "${probe_marker}"
then
  printf 'ERROR: runner sandbox could not write its private state directory.\n' >&2
  exit 1
fi
/usr/bin/rm -f "${probe_marker}"

printf 'Checking that private home and publisher credentials are hidden...\n'
if ! "${run[@]}" /usr/bin/test ! -e /home/adminvince/.ssh
then
  printf 'ERROR: runner sandbox exposed the private SSH directory.\n' >&2
  exit 1
fi
if ! "${run[@]}" /usr/bin/test ! -e "${repo}/.secrets/github-pages-deploy-key"
then
  printf 'ERROR: runner sandbox exposed the publisher deploy key.\n' >&2
  exit 1
fi

printf 'Checking that only the publisher sandbox can see its deploy key...\n'
if ! "${publisher_run[@]}" /usr/bin/test ! -e /home/adminvince/.ssh
then
  printf 'ERROR: publisher sandbox exposed the private SSH directory.\n' >&2
  exit 1
fi
if ! "${publisher_run[@]}" /usr/bin/test -r \
  "${repo}/.secrets/github-pages-deploy-key"
then
  printf 'ERROR: publisher sandbox could not read its repository deploy key.\n' >&2
  exit 1
fi

printf 'Checking that host Ollama remains reachable...\n'
if ! "${run[@]}" /usr/bin/curl --fail --silent --show-error --output /dev/null --max-time 5 \
  http://127.0.0.1:11434/api/tags
then
  printf 'ERROR: runner sandbox could not reach host Ollama.\n' >&2
  exit 1
fi


printf 'Checking OpenCode native read confinement end to end...\n'
if ! "${run[@]}" /usr/bin/env \
  "HOME=${probe_home}" \
  "TMPDIR=${probe_home}/tmp" \
  "XDG_DATA_HOME=${probe_home}/data" \
  "XDG_CACHE_HOME=${probe_home}/cache" \
  "XDG_CONFIG_HOME=${probe_home}/config" \
  "LANG=C.UTF-8" \
  "LC_ALL=C.UTF-8" \
  "OLLAMA_HOST=http://127.0.0.1:11434" \
  "NO_PROXY=127.0.0.1,localhost" \
  "OPENCODE_CONFIG_CONTENT=${opencode_config}" \
  "OPENCODE_DISABLE_AUTOUPDATE=true" \
  "OPENCODE_AUTO_SHARE=false" \
  "${repo}/.runtime/opencode/node_modules/.bin/opencode" \
  --pure run \
  --dir "${probe_stage}" \
  --model "${probe_model}" \
  --agent build \
  --format json \
  --auto \
  "${probe_prompt}" \
  >"${probe_events}" 2>"${probe_stderr}"
then
  printf 'ERROR: OpenCode isolation probe did not complete.\n' >&2
  exit 1
fi
if ! /usr/bin/grep -Fq "${inside_marker}" "${probe_events}"
then
  printf 'ERROR: OpenCode did not demonstrate a successful staged read.\n' >&2
  exit 1
fi
if ! /usr/bin/grep -Fq "${probe_outside}" "${probe_events}" ||
  /usr/bin/grep -Fq "${outside_marker}" "${probe_events}"
then
  printf 'ERROR: OpenCode outside-read denial was not proven or leaked content.\n' >&2
  exit 1
fi

printf 'Checking that the public internet is blocked...\n'
if "${run[@]}" /usr/bin/curl --fail --silent --show-error --output /dev/null --max-time 5 \
  https://github.com
then
  printf 'ERROR: runner isolation allowed public network access.\n' >&2
  exit 1
fi

printf 'Runner filesystem and network isolation probes passed.\n'
