#!/usr/bin/env bash
# register_hook: scan_terraform
# register_hook: scan_tofu

findings="$(find . -name "unwanted_file")"

if [[ "${findings}" ]]; then
  exit 230
fi
