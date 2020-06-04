#!/usr/bin/env ash

set -u # nounset
set -o pipefail

if [ $# -eq 0 ]; then
  # Print select pakage versions then open an ash shell
  ansible --version | head -1
  aws --version
  terraform version

  /usr/bin/env ash
else
  # Run the CMD
  eval "$@"
fi

