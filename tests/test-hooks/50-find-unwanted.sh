#!/usr/bin/env bash
# register_hook: scan_terraform

findings="$(find . -name "unwanted_file")"

if [[ "${findings}" ]]; then
  exit 230
fi
