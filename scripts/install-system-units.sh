#!/usr/bin/env bash
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
unit_dir="/etc/systemd/system"

install -d -m 0700 "${repo}/.lab-state"

for unit in agent-farm-run.service agent-farm-publish.service agent-farm-run.timer agent-farm-publish.timer; do
  sudo install -o root -g root -m 0644 \
    "${repo}/lab/systemd/${unit}" "${unit_dir}/${unit}"
done

sudo systemctl daemon-reload
sudo systemd-analyze verify \
  "${unit_dir}/agent-farm-run.service" \
  "${unit_dir}/agent-farm-publish.service" \
  "${unit_dir}/agent-farm-run.timer" \
  "${unit_dir}/agent-farm-publish.timer"

printf '\nSystem units installed but not enabled.\n'
printf 'Enable only after the network probes and a manual turn pass.\n'
