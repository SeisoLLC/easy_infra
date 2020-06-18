#!/usr/bin/env bash

set -o errexit
set -o nounset
set -o pipefail

if [ $# -eq 0 ]; then
  # Print select package versions then open an bash shell
  ansible --version | head -1
  aws --version | awk -F' ' '{print $1}'
  terraform version

  exec bash
else
  eval "BASH_ENV=${BASH_ENV} $*"
fi

