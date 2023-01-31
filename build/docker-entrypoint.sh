#!/usr/bin/env bash

# Intentionally not setting errexit to allow list constructs[1] in the docker run
# 1:  https://www.tldp.org/LDP/abs/html/list-cons.html

set -o pipefail
shopt -s dotglob
# shellcheck disable=SC1091
source /usr/local/bin/common.sh

function dequeue() {
  # Watch the fluent-bit process
  tail --pid="$(pidof fluent-bit)" -f /dev/null &

  # Sleep for twice the service flush interval from fluent-bit.conf
  sleep .2s

  # Have fluent-bit dequeue and then exit
  kill -SIGTERM "$(pidof fluent-bit)"

  # And then wait for it to exit
  wait

  _feedback DEBUGGING "Successfully dequeud fluent-bit, shutting down easy_infra..."
}

function interrupt() {
  # Log the interruption
  _log "easy_infra.stdouterr" info unknown "interruption" "${PWD}" string "Captured a SIGNIT"

  dequeue

  exit 230
}

trap dequeue EXIT
trap interrupt INT TERM

# The fluent-bit banner and other logs go to stderr, but warnings and errors go
# to stdout
fluent-bit -c /usr/local/etc/fluent-bit/fluent-bit.conf --verbose 2>/dev/null

# Clone the provided repositories when configured
if [[ -v "VCS_DOMAIN" && -v "CLONE_REPOSITORIES" ]]; then
  _clone "${VCS_DOMAIN}" "${CLONE_REPOSITORIES}" "${CLONE_PROTOCOL:-ssh}" "${CLONE_DIRECTORY:-/iac}"
fi

if [[ -x "$(which strace)" ]]; then
  strace -t -o /tmp/strace-fluent-bit -fp "$(pidof fluent-bit)" &
  sleep .2

  if ! pidof strace ; then
    _feedback WARNING "strace failed; consider adding -u 0 --cap-add=SYS_PTRACE to your docker run"
  fi
fi

if [ "$#" -eq 0 ]; then
  # Print select tool versions then open an bash shell
  if [ -x "$(which aws)" ]; then
    echo -e "aws-cli\t\t ${AWS_CLI_VERSION}"
  fi
  if [ -x "$(which az)" ]; then
    echo -e "azure-cli\t ${AZURE_CLI_VERSION}"
  fi
  if [ -x "$(which ansible)" ]; then
    echo -e "ansible\t\t ${ANSIBLE_VERSION}"
  fi
  if [ -x "$(which terraform)" ]; then
    current_version=$(cat /home/easy_infra/.tfenv/version)
    if [[ "${TERRAFORM_VERSION}" != "${current_version}" ]]; then
      echo -e "terraform\t ${TERRAFORM_VERSION} (customized)"
    else
      echo -e "terraform\t ${TERRAFORM_VERSION}"
    fi
  fi

  exec bash
else
  "$@" # Ensures that we always have a shell. exec "$@" works when we are passed `/bin/bash -c "example"`, but not just `example`; the latter will
       # bypass the shims because it doesn't have a BASH_ENV equivalent
fi
