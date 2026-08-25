#!/usr/bin/env bash
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
unit_dir="/etc/systemd/system"

for unit in agent-farm-run.service agent-farm-publish.service agent-farm-run.timer; do
  sudo install -o root -g root -m 0644 \
    "${repo}/lab/systemd/${unit}" "${unit_dir}/${unit}"
done

sudo systemctl daemon-reload
sudo systemd-analyze verify \
  "${unit_dir}/agent-farm-run.service" \
  "${unit_dir}/agent-farm-publish.service" \
  "${unit_dir}/agent-farm-run.timer"

printf '\nSystem units installed but not enabled.\n'
printf 'Enable only after the network probes and a manual turn pass.\n'

