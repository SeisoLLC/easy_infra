#!/usr/bin/env bash
# This is a script to test various details of the docker image

set -o nounset
set -o errexit
set -o errtrap
set -o pipefail

DANGLING_FILES="$(find / \( -path /proc                 \
                        -or -path /root                 \
                        -or -path /etc/ssl/private      \
                        -or -path /var/cache/ldconfig   \
                        -or -path /iac \) -prune -false \
                        -or -not -path /iac             \
                        -and -nogroup -nouser)"

if [[ "${DANGLING_FILES}" ]]; then
  echo "The following files do not have the right user or group ownership"
  echo "${DANGLING_FILES}"
  exit 1
fi
