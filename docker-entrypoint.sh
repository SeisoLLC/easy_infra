#!/usr/bin/env bash

# Intentionally not setting errexit to allow list constructs[1] in the docker run
# 1:  https://www.tldp.org/LDP/abs/html/list-cons.html

set -o nounset
set -o pipefail

if [ $# -eq 0 ]; then
  # Print select package versions then open an bash shell
  command ansible --version | head -1
  command aws --version | awk -F' ' '{print $1}'
  command terraform version

  exec bash
else
  eval BASH_ENV="${BASH_ENV}" "$@"
fi

