#!/usr/bin/env bash

set -u # nounset
set -o pipefail

if [ $# -eq 0 ]; then
  # Print select pakage versions then open an ash shell
  ansible --version | head -1
  aws --version
  terraform version

  exec bash
else
  # Run the CMD. Consider `exec "$@"` if you only need one command at a time,
  # as multiple commands are ugly with that approach
  eval "$@"
fi

